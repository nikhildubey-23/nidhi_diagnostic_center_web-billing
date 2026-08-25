"""Admin payments: list + record additional payments."""
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.billing import PAYMENT_METHODS, Invoice, Payment
from app.utils.helpers import log_audit, permission_required

payments_bp = Blueprint("payments", __name__)


@payments_bp.route("/")
@login_required
@permission_required("payments.manage")
def index():
    page = request.args.get("page", 1, type=int)
    method = request.args.get("method") or ""
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    from datetime import date, datetime, timedelta

    query = Payment.query.join(Invoice).filter(Payment.invoice_id == Invoice.id)
    if method in dict(PAYMENT_METHODS):
        query = query.filter(Payment.method == method)
    if date_from:
        try:
            d = date.fromisoformat(date_from)
            query = query.filter(Payment.paid_at >= datetime(d.year, d.month, d.day))
        except ValueError:
            pass
    if date_to:
        try:
            d = date.fromisoformat(date_to)
            query = query.filter(
                Payment.paid_at < datetime(d.year, d.month, d.day) + timedelta(days=1))
        except ValueError:
            pass
    pagination = query.order_by(Payment.paid_at.desc()).paginate(page=page, per_page=25)
    # re-apply filters for the sum
    sum_query = db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0)) \
        .join(Invoice, Payment.invoice_id == Invoice.id)
    if method in dict(PAYMENT_METHODS):
        sum_query = sum_query.filter(Payment.method == method)
    if date_from:
        try:
            d = date.fromisoformat(date_from)
            sum_query = sum_query.filter(Payment.paid_at >= datetime(d.year, d.month, d.day))
        except ValueError:
            pass
    if date_to:
        try:
            d = date.fromisoformat(date_to)
            sum_query = sum_query.filter(
                Payment.paid_at < datetime(d.year, d.month, d.day) + timedelta(days=1))
        except ValueError:
            pass
    total_sum = float(sum_query.scalar() or 0)

    return render_template("admin/payments/index.html",
                           pagination=pagination,
                           methods=PAYMENT_METHODS,
                           total=total_sum,
                           filters={"method": method, "from": date_from or "",
                                    "to": date_to or ""})


@payments_bp.route("/record/<int:invoice_id>", methods=["POST"])
@login_required
@permission_required("payments.manage")
def record(invoice_id):
    invoice = db.get_or_404(Invoice, invoice_id)
    amount_raw = request.form.get("amount", "0").strip()
    method = request.form.get("method", "")
    reference_no = (request.form.get("reference_no") or "").strip() or None
    notes = (request.form.get("notes") or "").strip() or None
    try:
        amount = Decimal(amount_raw)
    except Exception:
        amount = Decimal("0")

    try:
        payment = invoice.add_payment(amount, method, received_by=current_user.id,
                                      reference_no=reference_no, notes=notes)
        log_audit("payment_recorded", "payment", payment.id,
                  {"invoice": invoice.invoice_code, "amount": float(amount),
                   "method": method})
        db.session.commit()
        flash(f"Payment of \u20b9{amount:,.2f} recorded on {invoice.invoice_code}.",
              "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(request.referrer or url_for("invoices.view", invoice_id=invoice.id))
