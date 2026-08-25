"""Admin dashboard with KPIs and chart data."""
import calendar
import json
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required
from sqlalchemy import func

from app.extensions import db
from app.models.billing import Invoice, Payment
from app.models.booking import Booking
from app.models.patient import Patient
from app.utils.helpers import permission_required

admin_dash_bp = Blueprint("admin_dash", __name__)


def _day_bounds(d: date):
    start = datetime(d.year, d.month, d.day)
    return start, start + timedelta(days=1)


@admin_dash_bp.route("/")
@login_required
@permission_required("dashboard.view")
def dashboard():
    today = date.today()
    t0, t1 = _day_bounds(today)

    stats = {
        "bookings_today": Booking.query.filter(
            Booking.created_at.between(t0, t1)).count(),
        "patients_today": Patient.query.filter(
            Patient.created_at.between(t0, t1)).count(),
        "invoices_today": Invoice.query.filter(
            Invoice.created_at.between(t0, t1),
            Invoice.status != "cancelled").count(),
        "pending_bookings": Booking.query.filter_by(status="pending").count(),
        "confirmed_bookings": Booking.query.filter_by(status="confirmed").count(),
        "cancelled_bookings": Booking.query.filter(
            Booking.status.in_(["cancelled", "no_show"])).count(),
        "completed_tests_today": Booking.query.filter(
            Booking.status == "completed",
            Booking.completed_at.between(t0, t1)).count(),
    }

    # Today's collection (payments received today)
    paid_today = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.paid_at.between(t0, t1)).scalar()
    )
    stats["collection_today"] = float(paid_today or 0)

    pending_amount = (
        db.session.query(func.coalesce(func.sum(Invoice.balance_due), 0))
        .filter(Invoice.status.in_(["finalized", "partially_paid"])).scalar()
    )
    stats["pending_payments_amount"] = float(pending_amount or 0)

    recent_invoices = (
        Invoice.query.filter(Invoice.status != "draft")
        .order_by(Invoice.created_at.desc()).limit(8).all()
    )
    recent_bookings = Booking.query.order_by(Booking.created_at.desc()).limit(8).all()

    upcoming = (
        Booking.query.filter(Booking.status.in_(["pending", "confirmed"]),
                             Booking.preferred_date >= today)
        .order_by(Booking.preferred_date).limit(8).all()
    )

    return render_template("admin/dashboard/index.html", stats=stats,
                           recent_invoices=recent_invoices,
                           recent_bookings=recent_bookings,
                           upcoming=upcoming, today=today)


@admin_dash_bp.route("/charts/data")
@login_required
@permission_required("dashboard.view")
def charts_data():
    """Chart datasets with optional date range filters."""
    days = request.args.get("days", type=int) or 30
    end = request.args.get("end")
    end_date = date.fromisoformat(end) if end else date.today()
    start_date = end_date - timedelta(days=days - 1)

    s_dt = datetime(start_date.year, start_date.month, start_date.day)
    e_dt = datetime(end_date.year, end_date.month, end_date.day) + timedelta(days=1)

    # Daily revenue (payments)
    rows = (
        db.session.query(func.date(Payment.paid_at), func.sum(Payment.amount))
        .filter(Payment.paid_at.between(s_dt, e_dt))
        .group_by(func.date(Payment.paid_at))
        .all()
    )
    rev_map = {str(r[0]): float(r[1] or 0) for r in rows}

    labels, revenue = [], []
    cur = start_date
    while cur <= end_date:
        labels.append(cur.strftime("%d %b"))
        revenue.append(rev_map.get(cur.isoformat(), 0))
        cur += timedelta(days=1)

    # Monthly revenue (last 12 months)
    m_rows = (
        db.session.query(
            func.strftime("%Y-%m", Payment.paid_at)
            if db.engine.name == "sqlite" else func.date_format(Payment.paid_at, "%Y-%m"),
            func.sum(Payment.amount))
        .group_by(func.strftime("%Y-%m", Payment.paid_at)
                  if db.engine.name == "sqlite" else func.date_format(Payment.paid_at, "%Y-%m"))
        .order_by(func.strftime("%Y-%m", Payment.paid_at)
                  if db.engine.name == "sqlite" else func.date_format(Payment.paid_at, "%Y-%m"))
        .limit(12).all()
    )
    month_labels = [calendar.month_abbr[int(m.split("-")[1])] + " " + m.split("-")[0][2:]
                    for m, _ in m_rows]
    month_values = [float(v or 0) for _, v in m_rows]

    # Booking trend by day
    b_rows = (
        db.session.query(func.date(Booking.created_at), func.count(Booking.id))
        .filter(Booking.created_at.between(s_dt, e_dt))
        .group_by(func.date(Booking.created_at)).all()
    )
    b_map = {str(r[0]): int(r[1]) for r in b_rows}
    bookings_trend = [b_map.get(cur.isoformat(), 0) for cur in _iter_days(start_date, end_date)]

    # Test/service-wise sales (invoice items joined to services/categories)
    from app.models.billing import InvoiceItem
    from app.models.service import ServiceCategory
    svc_rows = (
        db.session.query(ServiceCategory.name,
                         func.sum(InvoiceItem.line_subtotal - InvoiceItem.discount_amount))
        .join(InvoiceItem.service)
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .filter(Invoice.status.in_(["finalized", "partially_paid", "paid"]),
                Invoice.created_at.between(s_dt, e_dt))
        .group_by(ServiceCategory.name).all()
    )
    svc_labels = [r[0] for r in svc_rows]
    svc_values = [float(r[1] or 0) for r in svc_rows]

    return jsonify({
        "daily_revenue": {"labels": labels, "values": revenue},
        "monthly_revenue": {"labels": month_labels, "values": month_values},
        "booking_trend": {"labels": labels, "values": bookings_trend},
        "service_sales": {"labels": svc_labels, "values": svc_values},
    })


def _iter_days(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)
