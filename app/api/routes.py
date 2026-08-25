"""JSON API v1 — used by admin UI (search, chart data)."""
from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app.extensions import db
from app.models.booking import Booking
from app.models.billing import Invoice
from app.models.patient import Patient
from app.models.service import Service

api_bp = Blueprint("api", __name__)


def _require_permission(code):
    if not current_user.is_authenticated or not current_user.has_permission(code):
        return False
    return True


@api_bp.route("/search")
@login_required
def global_search():
    """Global search: patients, invoices, bookings."""
    term = (request.args.get("q") or "").strip()
    if len(term) < 2:
        return jsonify({"patients": [], "invoices": [], "bookings": []})
    like = f"%{term}%"

    patients = []
    invoices = []
    bookings = []

    if _require_permission("patients.manage"):
        for p in Patient.query.filter(
                Patient.is_active.is_(True),
                or_(Patient.full_name.ilike(like),
                    Patient.mobile.ilike(like),
                    Patient.patient_code.ilike(f"{term}%"))).limit(6):
            patients.append(p.to_dict())

    if _require_permission("billing.manage"):
        for i in Invoice.query.filter(
                Invoice.invoice_code.ilike(f"{term}%"),
                Invoice.status != "cancelled").limit(6):
            invoices.append(i.to_dict())

    if _require_permission("bookings.manage"):
        for b in Booking.query.filter(
                or_(Booking.booking_code.ilike(f"{term}%"),
                    Booking.patient_name.ilike(like),
                    Booking.mobile.ilike(like))).limit(6):
            bookings.append(b.to_dict())

    return jsonify({"patients": patients, "invoices": invoices,
                    "bookings": bookings})


@api_bp.route("/services")
@login_required
def services():
    """Active services with DB prices (for invoice builder previews)."""
    rows = Service.query.filter_by(is_active=True).order_by(Service.name).all()
    return jsonify({"services": [s.to_dict() for s in rows]})


@api_bp.route("/dashboard/summary")
@login_required
def dashboard_summary():
    if not _require_permission("dashboard.view"):
        return jsonify(error="forbidden"), 403
    from datetime import date, datetime, timedelta

    today = date.today()
    t0 = datetime(today.year, today.month, today.day)
    t1 = t0 + timedelta(days=1)
    data = {
        "date": today.isoformat(),
        "bookings_today": Booking.query.filter(Booking.created_at.between(t0, t1)).count(),
        "pending_bookings": Booking.query.filter_by(status="pending").count(),
        "collection_today": float(
            db.session.query(func.coalesce(func.sum(Payment_amount()), 0))
            .filter(Paid_between(t0, t1)).scalar() or 0),
    }
    return jsonify(data)


def Payment_amount():
    from app.models.billing import Payment
    return Payment.amount


def Paid_between(t0, t1):
    from app.models.billing import Payment
    return Payment.paid_at.between(t0, t1)
