"""Admin billing counter — fast invoice creation workflow.

Search patient → select/create → add services → discounts → payment method
→ generate invoice → finalize/print. All money math is server-side.
"""
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy import or_
from wtforms import (
    DateField, EmailField, IntegerField, RadioField, SelectField,
    StringField, TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Regexp

from app.extensions import db
from app.models.billing import PAYMENT_METHODS, Invoice, InvoiceItem
from app.models.booking import Booking
from app.models.patient import Patient
from app.models.service import Service
from app.services.notifications import notify_invoice_created
from app.utils.helpers import log_audit, permission_required
from app.utils.numbering import next_invoice_code, next_patient_code

billing_bp = Blueprint("billing", __name__)


class QuickPatientForm(FlaskForm):
    full_name = StringField(validators=[DataRequired(), Length(2, 128)])
    mobile = StringField(validators=[DataRequired(), Regexp(r"^[6-9]\d{9}$")])
    email = EmailField(validators=[Optional(), Length(max=254)])
    age = IntegerField(validators=[Optional(), NumberRange(0, 120)])
    gender = RadioField(choices=[("male", "Male"), ("female", "Female"), ("other", "Other")],
                        validators=[DataRequired()])
    address = TextAreaField(validators=[Optional(), Length(max=500)])


def _search_patients(term: str):
    term = (term or "").strip()
    if not term:
        return []
    like = f"%{term}%"
    return (Patient.query.filter_by(is_active=True)
            .filter(or_(Patient.full_name.ilike(like),
                        Patient.mobile.ilike(like),
                        Patient.patient_code.ilike(f"{term}%")))
            .order_by(Patient.full_name).limit(10).all())


@billing_bp.route("/", methods=["GET"])
@login_required
@permission_required("billing.manage")
def counter():
    """Main billing counter page."""
    q = request.args.get("q", "")
    patients = _search_patients(q)
    new_form = QuickPatientForm()
    services = (Service.query.filter_by(is_active=True)
                .order_by(Service.name).all())
    return render_template("admin/billing/counter.html",
                           patients=patients, q=q, form=new_form, services=services)


@billing_bp.route("/new-invoice")
@login_required
@permission_required("billing.manage")
def new_invoice():
    """Invoice builder for a selected (existing or just-created) patient."""
    patient_id = request.args.get("patient_id", type=int)
    booking_id = request.args.get("booking_id", type=int)
    patient = None
    if patient_id:
        patient = db.session.get(Patient, patient_id)
        if patient is None:
            flash("Patient not found.", "danger")
            return redirect(url_for(".counter"))
    services = (Service.query.filter_by(is_active=True)
                .order_by(Service.name).all())
    booking = db.session.get(Booking, booking_id) if booking_id else None
    return render_template("admin/billing/new_invoice.html",
                           patient=patient, services=services, booking=booking)


@billing_bp.route("/create-patient", methods=["POST"])
@login_required
@permission_required("patients.manage")
def create_patient():
    """Quick-create a patient at the counter then continue to invoicing."""
    form = QuickPatientForm()
    if form.validate_on_submit():
        existing = Patient.query.filter_by(mobile=form.mobile.data.strip()).first()
        if existing:
            flash(f"Existing patient found for this number: "
                  f"{existing.full_name} ({existing.patient_code}).", "info")
            return redirect(url_for(".new_invoice", patient_id=existing.id))
        patient = Patient(patient_code=next_patient_code())
        form.populate_obj(patient)
        patient.mobile = form.mobile.data.strip()
        db.session.add(patient)
        db.session.flush()
        log_audit("patient_created", "patient", patient.id,
                  {"code": patient.patient_code, "via": "counter"})
        db.session.commit()
        flash(f"Patient {patient.full_name} ({patient.patient_code}) created.", "success")
        return redirect(url_for(".new_invoice", patient_id=patient.id))
    for field, errors in form.errors.items():
        for err in errors:
            flash(err, "danger")
    return redirect(url_for(".counter"))


@billing_bp.route("/create-invoice", methods=["POST"])
@login_required
@permission_required("billing.manage")
def create_invoice():
    """Build the draft invoice from posted service selections.

    Security: rates/taxes are ALWAYS re-read from the database; client-sent
    prices/discounts/totals are ignored except per-item discount which is
    validated against eligibility and capped.
    """
    patient_id = request.form.get("patient_id", type=int)
    booking_id = request.form.get("booking_id", type=int)
    patient = db.session.get(Patient, patient_id) if patient_id else None
    if patient is None:
        flash("Select a valid patient first.", "danger")
        return redirect(url_for(".counter"))

    # item payload: service_<id> qty + discount_<id>
    items_spec = []
    for svc in Service.query.filter_by(is_active=True).all():
        key_qty = request.form.get(f"qty_{svc.id}", type=int)
        key_add = request.form.get(f"add_{svc.id}")
        qty = key_qty if (key_add or key_qty) else 0
        if not qty or qty < 1:
            continue
        qty = min(qty, 20)  # sanity cap
        disc = Decimal(request.form.get(f"discount_{svc.id}", "0") or "0")
        if not svc.discount_eligible:
            disc = Decimal("0")
        rate = Decimal(svc.price)
        max_disc = rate * qty  # cannot exceed line value; cap at 100%
        if disc < 0:
            disc = Decimal("0")
        if disc > max_disc:
            disc = max_disc
        items_spec.append((svc, qty, disc))

    if not items_spec:
        flash("Add at least one service/test to the invoice.", "danger")
        return redirect(url_for(".new_invoice",
                                **({"patient_id": patient.id} |
                                   ({"booking_id": booking_id} if booking_id else {}))))

    other_charges = Decimal(request.form.get("other_charges", "0") or "0")
    if other_charges < 0:
        other_charges = Decimal("0")

    notes = (request.form.get("notes") or "").strip() or None

    invoice = Invoice(
        invoice_code=next_invoice_code(),
        patient_id=patient.id,
        booking_id=booking_id if booking_id else None,
        created_by_id=current_user.id,
        other_charges=other_charges,
        notes=notes,
        terms_snapshot=request.form.get("terms_snapshot"),
    )
    from app.utils.helpers import get_setting
    invoice.terms_snapshot = invoice.terms_snapshot or get_setting("invoice_terms")

    for svc, qty, disc in items_spec:
        invoice.items.append(InvoiceItem(
            service_id=svc.id, service_name_snapshot=svc.name,
            qty=qty, rate=Decimal(svc.price),
            discount_amount=disc, tax_percent=Decimal(svc.tax_percent or 0),
        ))

    # Payment (optional at creation time)
    pay_amount = Decimal(request.form.get("pay_amount", "0") or "0")
    pay_method = request.form.get("pay_method") or ""
    action = request.form.get("action", "draft")

    invoice.recalculate()
    db.session.add(invoice)
    db.session.flush()

    try:
        if action == "finalize":
            invoice.finalize(user_id=current_user.id)
            if pay_amount > 0:
                if pay_method not in dict(PAYMENT_METHODS):
                    raise ValueError("Choose a valid payment method.")
                invoice.add_payment(pay_amount, pay_method,
                                    received_by=current_user.id)
            log_audit("invoice_finalized", "invoice", invoice.id,
                      {"code": invoice.invoice_code})
            notify_invoice_created(invoice)
        else:
            log_audit("invoice_drafted", "invoice", invoice.id,
                      {"code": invoice.invoice_code})
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for(".new_invoice", patient_id=patient.id,
                                **({"booking_id": booking_id} if booking_id else {})))

    db.session.commit()
    flash(f"Invoice {invoice.invoice_code} "
          f"{'finalized' if invoice.status != 'draft' else 'saved as draft'}.", "success")
    if action == "finalize":
        return redirect(url_for("invoices.view", invoice_id=invoice.id, print_=1))
    return redirect(url_for("invoices.view", invoice_id=invoice.id))


@billing_bp.route("/drafts")
@login_required
@permission_required("billing.manage")
def drafts():
    page = request.args.get("page", 1, type=int)
    pagination = (Invoice.query.filter_by(status="draft")
                  .order_by(Invoice.created_at.desc())
                  .paginate(page=page, per_page=20))
    return render_template("admin/billing/drafts.html", pagination=pagination)


@billing_bp.route("/price-preview", methods=["GET"])
@login_required
@permission_required("billing.manage")
def price_preview():
    """Return DB prices for selected services so the UI can show live totals.
    The authoritative calculation still happens on submit."""
    ids = request.args.getlist("ids", type=int)
    data = []
    for sid in ids[:30]:
        svc = db.session.get(Service, sid)
        if svc and svc.is_active:
            data.append({"id": svc.id, "name": svc.name,
                         "rate": float(svc.price),
                         "tax_percent": float(svc.tax_percent or 0),
                         "discount_eligible": svc.discount_eligible})
    return {"items": data}
