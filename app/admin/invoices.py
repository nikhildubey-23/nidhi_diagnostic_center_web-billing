"""Admin invoice actions: view, print, PDF, finalize, cancel, edit-draft."""
from decimal import Decimal

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.extensions import db
from app.models.billing import PAYMENT_METHODS, Invoice, InvoiceItem, Payment
from app.services.notifications import notify_invoice_created
from app.services.pdf_invoice import send_invoice_pdf
from app.utils.helpers import log_audit, permission_required

invoices_bp = Blueprint("invoices", __name__)


@invoices_bp.route("/")
@login_required
@permission_required("billing.manage")
def index():
    page = request.args.get("page", 1, type=int)
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status") or ""
    date_from = request.args.get("from")
    date_to = request.args.get("to")

    from datetime import date, datetime, timedelta

    query = Invoice.query
    if q:
        like = f"%{q}%"
        query = query.join(Invoice.patient).filter(or_(
            Invoice.invoice_code.ilike(like),
            Invoice.patient.has(Patient_full_name_like(like)),
            Invoice.patient.has(Patient_mobile_like(like)),
        ))
    if status in dict_status():
        query = query.filter(Invoice.status == status)
    if date_from:
        try:
            d = date.fromisoformat(date_from)
            query = query.filter(Invoice.created_at >= datetime(d.year, d.month, d.day))
        except ValueError:
            pass
    if date_to:
        try:
            d = date.fromisoformat(date_to)
            query = query.filter(
                Invoice.created_at < datetime(d.year, d.month, d.day) + timedelta(days=1))
        except ValueError:
            pass

    pagination = query.order_by(Invoice.created_at.desc()).paginate(page=page, per_page=20)
    return render_template("admin/invoices/index.html",
                           pagination=pagination,
                           statuses=[("draft", "Draft"), ("finalized", "Finalized"),
                                     ("partially_paid", "Partially Paid"),
                                     ("paid", "Paid"), ("cancelled", "Cancelled")],
                           filters={"q": q, "status": status,
                                    "from": date_from or "", "to": date_to or ""})


def Patient_full_name_like(like):
    from app.models.patient import Patient
    return Patient.full_name.ilike(like)


def Patient_mobile_like(like):
    from app.models.patient import Patient
    return Patient.mobile.ilike(like)


def dict_status():
    from app.models.billing import INVOICE_STATUSES
    return dict(INVOICE_STATUSES)


@invoices_bp.route("/<int:invoice_id>")
@login_required
@permission_required("billing.manage")
def view(invoice_id):
    invoice = db.get_or_404(Invoice, invoice_id)
    auto_print = request.args.get("print_", type=int) == 1 and invoice.status != "draft"
    return render_template("admin/invoices/view.html", invoice=invoice,
                           payment_methods=PAYMENT_METHODS, auto_print=auto_print)


@invoices_bp.route("/<int:invoice_id>/print")
@login_required
@permission_required("billing.manage")
def print_view(invoice_id):
    invoice = db.get_or_404(Invoice, invoice_id)
    if invoice.status == "draft":
        flash("Finalize the draft before printing.", "warning")
        return redirect(url_for(".view", invoice_id=invoice.id))
    return render_template("admin/invoices/print.html", invoice=invoice)


@invoices_bp.route("/<int:invoice_id>/pdf")
@login_required
@permission_required("billing.manage")
def pdf(invoice_id):
    invoice = db.get_or_404(Invoice, invoice_id)
    if invoice.status == "draft":
        flash("Finalize the draft before downloading the PDF.", "warning")
        return redirect(url_for(".view", invoice_id=invoice.id))
    log_audit("invoice_pdf_downloaded", "invoice", invoice.id,
              {"code": invoice.invoice_code})
    db.session.commit()
    return send_invoice_pdf(invoice)


@invoices_bp.route("/<int:invoice_id>/finalize", methods=["POST"])
@login_required
@permission_required("billing.manage")
def finalize(invoice_id):
    invoice = db.get_or_404(Invoice, invoice_id)
    try:
        invoice.finalize(user_id=current_user.id)
        log_audit("invoice_finalized", "invoice", invoice.id,
                  {"code": invoice.invoice_code})
        notify_invoice_created(invoice)
        db.session.commit()
        flash(f"Invoice {invoice.invoice_code} finalized.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for(".view", invoice_id=invoice.id))


@invoices_bp.route("/<int:invoice_id>/cancel", methods=["POST"])
@login_required
@permission_required("billing.manage")
def cancel(invoice_id):
    invoice = db.get_or_404(Invoice, invoice_id)
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("A cancellation reason is required.", "danger")
        return redirect(url_for(".view", invoice_id=invoice.id))
    try:
        invoice.cancel(reason, user_id=current_user.id)
        log_audit("invoice_cancelled", "invoice", invoice.id,
                  {"code": invoice.invoice_code, "reason": reason})
        db.session.commit()
        flash(f"Invoice {invoice.invoice_code} cancelled (kept for records).", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for(".view", invoice_id=invoice.id))


@invoices_bp.route("/<int:invoice_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("billing.manage")
def edit_draft(invoice_id):
    """Only DRAFT invoices may be edited. Finalized invoices are immutable."""
    invoice = db.get_or_404(Invoice, invoice_id)
    if invoice.status != "draft":
        flash("Finalized invoices cannot be edited. Cancel and re-bill instead.", "warning")
        return redirect(url_for(".view", invoice_id=invoice.id))

    from app.models.service import Service
    services = Service.query.filter_by(is_active=True).order_by(Service.name).all()

    if request.method == "POST":
        # Rebuild items from posted selections with DB prices.
        invoice.items.clear()
        for svc in services:
            qty = request.form.get(f"qty_{svc.id}", type=int) or 0
            add = request.form.get(f"add_{svc.id}")
            qty = min(max(qty, 0), 20)
            if not (add or qty):
                continue
            disc = Decimal(request.form.get(f"discount_{svc.id}", "0") or "0")
            rate = Decimal(svc.price)
            if not svc.discount_eligible:
                disc = Decimal("0")
            disc = max(disc, Decimal("0"))
            disc = min(disc, rate * max(qty, 1))
            if qty >= 1:
                invoice.items.append(InvoiceItem(
                    service_id=svc.id, service_name_snapshot=svc.name,
                    qty=qty, rate=rate, discount_amount=disc,
                    tax_percent=Decimal(svc.tax_percent or 0)))
        try:
            invoice.other_charges = max(
                Decimal(request.form.get("other_charges", "0") or "0"), Decimal("0"))
        except Exception:
            pass
        invoice.notes = (request.form.get("notes") or "").strip() or None
        if not invoice.items:
            flash("An invoice needs at least one item.", "danger")
            return redirect(request.url)
        invoice.recalculate()
        log_audit("invoice_draft_edited", "invoice", invoice.id,
                  {"code": invoice.invoice_code})
        db.session.commit()
        flash("Draft updated.", "success")
        return redirect(url_for(".edit_draft", invoice_id=invoice.id))

    return render_template("admin/invoices/edit_draft.html", invoice=invoice,
                           services=services)
