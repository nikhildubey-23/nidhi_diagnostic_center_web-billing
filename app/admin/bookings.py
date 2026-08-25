"""Admin booking management."""
from datetime import date, datetime, timedelta

from flask import (
    Blueprint, current_app, flash, jsonify, redirect, render_template, request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_
from flask_wtf import FlaskForm
from wtforms import (
    DateField, EmailField, IntegerField, SelectField, StringField,
    TextAreaField, TimeField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Regexp

from app.extensions import db
from app.models.billing import Invoice
from app.models.booking import BOOKING_STATUSES, Booking
from app.models.patient import Patient
from app.models.service import Service
from app.utils.helpers import log_audit, permission_required
from app.utils.numbering import next_booking_code, next_invoice_code, next_patient_code

bookings_bp = Blueprint("bookings", __name__)


class BookingEditForm(FlaskForm):
    patient_name = StringField(validators=[DataRequired(), Length(2, 128)])
    mobile = StringField(validators=[DataRequired(), Regexp(r"^[6-9]\d{9}$")])
    email = EmailField(validators=[Optional(), Length(max=254)])
    age = IntegerField(validators=[Optional(), NumberRange(0, 120)])
    gender = SelectField(choices=[("", "Select"), ("male", "Male"),
                                  ("female", "Female"), ("other", "Other")])
    service_id = SelectField(coerce=int, validators=[DataRequired()])
    preferred_date = DateField(validators=[DataRequired()])
    preferred_time = TimeField(validators=[Optional()])
    address = TextAreaField(validators=[Optional(), Length(max=500)])
    notes = TextAreaField(validators=[Optional(), Length(max=1000)])


def _service_choices():
    services = Service.query.filter_by(is_active=True).order_by(Service.name).all()
    return [(s.id, f"{s.name} ({s.code})") for s in services]


@bookings_bp.route("/")
@login_required
@permission_required("bookings.manage")
def index():
    page = request.args.get("page", 1, type=int)
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status") or ""
    service_id = request.args.get("service_id", type=int)
    date_from = request.args.get("from", type=str)
    date_to = request.args.get("to", type=str)

    query = Booking.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Booking.patient_name.ilike(like),
            Booking.mobile.ilike(like),
            Booking.booking_code.ilike(like),
        ))
    if status in dict(BOOKING_STATUSES):
        query = query.filter(Booking.status == status)
    if service_id:
        query = query.filter(Booking.service_id == service_id)
    if date_from:
        d = date.fromisoformat(date_from)
        query = query.filter(Booking.preferred_date >= d)
    if date_to:
        d = date.fromisoformat(date_to)
        query = query.filter(Booking.preferred_date <= d)

    pagination = query.order_by(
        Booking.created_at.desc()).paginate(page=page, per_page=20)
    services = Service.query.filter_by(is_active=True).order_by(Service.name).all()
    return render_template("admin/bookings/index.html",
                           pagination=pagination, statuses=BOOKING_STATUSES,
                           services=services, filters={
                               "q": q, "status": status,
                               "service_id": service_id or "",
                               "from": date_from or "", "to": date_to or "",
                           })


@bookings_bp.route("/<int:booking_id>")
@login_required
@permission_required("bookings.manage")
def detail(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    invoices = booking.invoices.all()
    form = BookingEditForm(obj=booking)
    form.service_id.choices = _service_choices()
    if booking.service_id and not any(c[0] == booking.service_id for c in form.service_id.choices):
        form.service_id.choices.append((booking.service_id, str(booking.service)))
    return render_template("admin/bookings/detail.html", booking=booking,
                           invoices=invoices, form=form,
                           statuses=BOOKING_STATUSES)


@bookings_bp.route("/<int:booking_id>/status", methods=["POST"])
@login_required
@permission_required("bookings.manage")
def update_status(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    new_status = request.form.get("status", "")
    reason = (request.form.get("reason") or "").strip()

    if new_status not in dict(BOOKING_STATUSES):
        flash("Invalid status.", "danger")
        return redirect(url_for(".detail", booking_id=booking.id))
    if not booking.transition_allowed(new_status):
        flash(f"Cannot move booking from '{booking.status_label}' "
              f"to '{dict(BOOKING_STATUSES)[new_status]}'.", "danger")
        return redirect(url_for(".detail", booking_id=booking.id))

    now = datetime.now()
    booking.status = new_status
    if new_status == "confirmed":
        booking.confirmed_at = now
    elif new_status == "completed":
        booking.completed_at = now
    elif new_status in {"cancelled", "no_show"}:
        booking.cancelled_at = now
        booking.cancel_reason = reason or "Cancelled by staff"
    log_audit(f"booking_{new_status}", "booking", booking.id,
              {"code": booking.booking_code, "reason": reason})
    db.session.commit()
    flash(f"Booking {booking.booking_code} marked as {booking.status_label}.", "success")
    return redirect(request.referrer or url_for(".detail", booking_id=booking.id))


@bookings_bp.route("/<int:booking_id>/reschedule", methods=["POST"])
@login_required
@permission_required("bookings.manage")
def reschedule(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    try:
        new_date = date.fromisoformat(request.form.get("preferred_date", ""))
        t = request.form.get("preferred_time")
        new_time = datetime.strptime(t, "%H:%M").time() if t else None
    except ValueError:
        flash("Invalid date/time.", "danger")
        return redirect(url_for(".detail", booking_id=booking.id))
    booking.preferred_date = new_date
    booking.preferred_time = new_time
    log_audit("booking_rescheduled", "booking", booking.id,
              {"code": booking.booking_code, "to": str(new_date)})
    db.session.commit()
    flash("Booking rescheduled.", "success")
    return redirect(url_for(".detail", booking_id=booking.id))


@bookings_bp.route("/<int:booking_id>/edit", methods=["POST"])
@login_required
@permission_required("bookings.manage")
def edit(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    form = BookingEditForm(obj=booking)
    form.service_id.choices = _service_choices()
    if form.validate_on_submit():
        form.populate_obj(booking)
        log_audit("booking_updated", "booking", booking.id,
                  {"code": booking.booking_code})
        db.session.commit()
        flash("Booking updated.", "success")
    else:
        flash("Please correct the highlighted fields.", "danger")
    return redirect(url_for(".detail", booking_id=booking.id))


@bookings_bp.route("/<int:booking_id>/register-patient", methods=["POST"])
@login_required
@permission_required("patients.manage")
def register_patient(booking_id):
    """Link the booking to an existing patient (matched by mobile) or create one."""
    booking = db.get_or_404(Booking, booking_id)

    existing_id = request.form.get("patient_id", type=int)
    if existing_id:
        patient = db.session.get(Patient, existing_id)
        if patient is None:
            flash("Selected patient not found.", "danger")
            return redirect(url_for(".detail", booking_id=booking.id))
    else:
        # Re-use a patient with the same mobile number to avoid duplicates.
        patient = Patient.query.filter_by(mobile=booking.mobile).first()
        if patient is None:
            patient = Patient(
                patient_code=next_patient_code(),
                full_name=booking.patient_name,
                mobile=booking.mobile,
                email=booking.email,
                age=booking.age,
                gender=booking.gender,
                address=booking.address,
            )
            db.session.add(patient)
            db.session.flush()
            log_audit("patient_created", "patient", patient.id,
                      {"code": patient.patient_code, "via": "booking"})

    booking.patient_id = patient.id
    log_audit("booking_patient_linked", "booking", booking.id,
              {"code": booking.booking_code, "patient": patient.patient_code})
    db.session.commit()
    flash(f"Booking linked to patient {patient.full_name} ({patient.patient_code}).",
          "success")
    return redirect(url_for("billing.new_invoice", patient_id=patient.id))


@bookings_bp.route("/new", methods=["GET", "POST"])
@login_required
@permission_required("bookings.manage")
def create():
    """Staff-created (walk-in) booking."""
    form = BookingEditForm()
    form.service_id.choices = _service_choices()
    if form.validate_on_submit():
        svc = db.session.get(Service, form.service_id.data)
        booking = Booking(
            booking_code=next_booking_code(),
            patient_name=form.patient_name.data.strip(),
            mobile=form.mobile.data.strip(),
            email=(form.email.data or "").strip() or None,
            age=form.age.data,
            gender=form.gender.data or None,
            address=(form.address.data or "").strip() or None,
            notes=(form.notes.data or "").strip() or None,
            service_id=svc.id,
            preferred_date=form.preferred_date.data,
            preferred_time=form.preferred_time.data,
            status="confirmed" if form.preferred_date.data <= date.today() + timedelta(days=1) else "pending",
            source="walk_in",
            created_by_id=current_user.id,
        )
        db.session.add(booking)
        db.session.flush()
        log_audit("booking_created", "booking", booking.id,
                  {"code": booking.booking_code, "source": "admin"})
        db.session.commit()
        flash(f"Booking {booking.booking_code} created.", "success")
        return redirect(url_for(".detail", booking_id=booking.id))
    return render_template("admin/bookings/create.html", form=form)


@bookings_bp.route("/<int:booking_id>/invoice", methods=["POST"])
@login_required
@permission_required("billing.manage")
def make_invoice(booking_id):
    """Create a draft invoice for this booking's services."""
    booking = db.get_or_404(Booking, booking_id)
    if booking.patient_id is None:
        flash("Register/link the patient first.", "warning")
        return redirect(url_for(".detail", booking_id=booking.id))

    existing = booking.invoices.filter(
        Invoice.status.in_(["draft", "finalized", "partially_paid", "paid"])).first()
    if existing:
        return redirect(url_for("invoices.view", invoice_id=existing.id))

    from decimal import Decimal

    from app.models.billing import InvoiceItem

    invoice = Invoice(invoice_code=next_invoice_code(), patient_id=booking.patient_id,
                      booking_id=booking.id, created_by_id=current_user.id)
    service_ids = request.form.getlist("service_ids", type=int) or \
        [bs.service_id for bs in booking.services] or [booking.service_id]
    seen = set()
    for sid in service_ids:
        if sid in seen:
            continue
        seen.add(sid)
        svc = db.session.get(Service, sid)
        if svc and svc.is_active:
            invoice.items.append(InvoiceItem(service_id=svc.id,
                                             service_name_snapshot=svc.name,
                                             qty=1, rate=svc.price,
                                             tax_percent=svc.tax_percent))
    if not invoice.items:
        flash("No active services found to bill.", "danger")
        return redirect(url_for(".detail", booking_id=booking.id))
    invoice.recalculate()
    db.session.add(invoice)
    db.session.flush()
    log_audit("invoice_created", "invoice", invoice.id,
              {"code": invoice.invoice_code, "from_booking": booking.booking_code})
    db.session.commit()
    flash(f"Draft invoice {invoice.invoice_code} created.", "success")
    return redirect(url_for("invoices.view", invoice_id=invoice.id))
