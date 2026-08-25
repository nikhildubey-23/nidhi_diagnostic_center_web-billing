"""Financial reports + daily collection register."""
import csv
import io
from datetime import date, datetime, timedelta

from flask import Blueprint, Response, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import func

from app.extensions import db
from app.models.billing import Invoice, InvoiceItem, Payment
from app.models.booking import Booking
from app.models.patient import Patient
from app.models.service import ServiceCategory
from app.utils.helpers import log_audit, permission_required

finreports_bp = Blueprint("finreports", __name__)


def _range_from_args(args):
    preset = args.get("preset") or "today"
    today = date.today()
    if preset == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    if preset == "week":
        start = today - timedelta(days=today.weekday())
        return start, today
    if preset == "month":
        return today.replace(day=1), today
    if preset == "custom":
        try:
            start = date.fromisoformat(args.get("from") or "")
        except ValueError:
            start = today
        try:
            end = date.fromisoformat(args.get("to") or "")
        except ValueError:
            end = today
        if end < start:
            start, end = end, start
        return start, end
    return today, today  # today


def _bounds(start: date, end: date):
    s = datetime(start.year, start.month, start.day)
    e = datetime(end.year, end.month, end.day) + timedelta(days=1)
    return s, e


@finreports_bp.route("/")
@login_required
@permission_required("finreports.view")
def index():
    start, end = _range_from_args(request.args)
    s_dt, e_dt = _bounds(start, end)

    inv_q = Invoice.query.filter(
        Invoice.created_at.between(s_dt, e_dt),
        Invoice.status.in_(["finalized", "partially_paid", "paid"]))
    invoices = inv_q.all()

    totals = {
        "count": len(invoices),
        "sales": sum(float(i.subtotal or 0) for i in invoices),
        "discounts": sum(float(i.discount_amount or 0) for i in invoices),
        "tax": sum(float(i.tax_total or 0) for i in invoices),
        "other": sum(float(i.other_charges or 0) for i in invoices),
        "grand": sum(float(i.grand_total or 0) for i in invoices),
        "paid": sum(float(i.amount_paid or 0) for i in invoices),
        "outstanding": sum(float(i.balance_due or 0) for i in invoices),
    }

    # Category breakdown via items
    cat_rows = (
        db.session.query(
            ServiceCategory.name,
            func.sum(InvoiceItem.line_subtotal),
            func.count(InvoiceItem.id),
        )
        .join(InvoiceItem.service)
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .filter(Invoice.status.in_(["finalized", "partially_paid", "paid"]),
                Invoice.created_at.between(s_dt, e_dt))
        .group_by(ServiceCategory.name).all()
    )
    category_breakdown = [
        {"name": r[0], "sales": float(r[1] or 0), "items": int(r[2])}
        for r in cat_rows
    ]

    # Payment method breakdown
    pm_rows = (
        db.session.query(Payment.method, func.sum(Payment.amount), func.count(Payment.id))
        .filter(Payment.paid_at.between(s_dt, e_dt))
        .group_by(Payment.method).all()
    )
    from app.models.billing import PAYMENT_METHODS
    method_names = dict(PAYMENT_METHODS)
    method_breakdown = [
        {"method": method_names.get(r[0], r[0]), "amount": float(r[1] or 0),
         "count": int(r[2])}
        for r in pm_rows
    ]

    return render_template("admin/finreports/index.html",
                           start=start, end=end,
                           presets=["today", "yesterday", "week", "month", "custom"],
                           totals=totals,
                           category_breakdown=category_breakdown,
                           method_breakdown=method_breakdown)


@finreports_bp.route("/export")
@login_required
@permission_required("finreports.view")
def export():
    """CSV/Excel-compatible export of the invoice summary for a period."""
    fmt = request.args.get("format", "csv")
    start, end = _range_from_args(request.args)
    s_dt, e_dt = _bounds(start, end)

    invoices = (Invoice.query
                .filter(Invoice.created_at.between(s_dt, e_dt),
                        Invoice.status != "cancelled")
                .order_by(Invoice.created_at).all())

    if fmt == "pdf":
        return _export_pdf(invoices, start, end)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Invoice No", "Date", "Patient Code", "Patient",
                     "Mobile", "Subtotal", "Discount", "Tax", "Other",
                     "Grand Total", "Paid", "Balance", "Status"])
    for i in invoices:
        writer.writerow([
            i.invoice_code,
            i.created_at.strftime("%Y-%m-%d %H:%M"),
            i.patient.patient_code if i.patient else "",
            i.patient.full_name if i.patient else "",
            i.patient.mobile if i.patient else "",
            f"{i.subtotal:.2f}", f"{i.discount_amount:.2f}",
            f"{i.tax_total:.2f}", f"{i.other_charges:.2f}",
            f"{i.grand_total:.2f}", f"{i.amount_paid:.2f}",
            f"{i.balance_due:.2f}", i.status_label,
        ])
    buf.seek(0)
    filename = f"sales_{start.isoformat()}_{end.isoformat()}.csv"
    log_audit("finreport_exported", "invoice", None,
              {"from": str(start), "to": str(end), "format": "csv"})
    db.session.commit()
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _export_pdf(invoices, start, end):
    """Simple PDF listing of invoices for the period."""
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm)
    styles = getSampleStyleSheet()
    h = styles["Heading2"]
    small = ParagraphStyle("s", parent=styles["Normal"], fontSize=8.5)
    story = [
        Paragraph(f"Nidhi Diagnostic \u2014 Sales Report "
                  f"({start.strftime('%d %b %Y')} to {end.strftime('%d %b %Y')})", h),
        Spacer(1, 10),
    ]
    data = [["Invoice", "Date", "Patient", "Grand Total", "Paid", "Balance", "Status"]]
    g = p = b = 0.0
    for i in invoices:
        data.append([
            i.invoice_code,
            i.created_at.strftime("%d %b %H:%M"),
            i.patient.full_name if i.patient else "",
            f"{float(i.grand_total):,.2f}", f"{float(i.amount_paid):,.2f}",
            f"{float(i.balance_due):,.2f}", i.status_label])
        g += float(i.grand_total); p += float(i.amount_paid); b += float(i.balance_due)
    data.append(["TOTAL", "", "", f"{g:,.2f}", f"{p:,.2f}", f"{b:,.2f}", ""])
    t = Table(data, repeatRows=1, colWidths=[110, 70, None, 75, 75, 75, 80])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    doc.build(story)
    buf.seek(0)
    from flask import send_file
    log_audit("finreport_exported", "invoice", None,
              {"from": str(start), "to": str(end), "format": "pdf"})
    db.session.commit()
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=f"sales_{start}_{end}.pdf")


# ---------------------------------------------------------------------------
# Daily collection register
# ---------------------------------------------------------------------------

@finreports_bp.route("/daily-collection")
@login_required
@permission_required("finreports.view")
def daily_collection():
    d_raw = request.args.get("date")
    try:
        day = date.fromisoformat(d_raw) if d_raw else date.today()
    except ValueError:
        day = date.today()
    s_dt, e_dt = _bounds(day, day)

    rows = (
        db.session.query(
            Payment, Invoice, Patient,
        )
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .join(Patient, Invoice.patient_id == Patient.id)
        .filter(Payment.paid_at.between(s_dt, e_dt))
        .order_by(Payment.paid_at)
        .all()
    )

    total = sum(float(p.amount) for p, _, _ in rows)
    by_method = {}
    from app.models.billing import PAYMENT_METHODS
    method_names = dict(PAYMENT_METHODS)
    for p, _, _ in rows:
        label = method_names.get(p.method, p.method.title())
        by_method[label] = by_method.get(label, 0) + float(p.amount)

    staff_names = {}
    from app.models.user import User
    user_ids = {p.received_by_id for p, _, _ in rows if p.received_by_id}
    for u in User.query.filter(User.id.in_(user_ids)).all() if user_ids else []:
        staff_names[u.id] = u.full_name or u.username

    entries = [{
        "invoice_id": inv.id,
        "time": p.paid_at.strftime("%I:%M %p"),
        "invoice": inv.invoice_code,
        "patient": pat.full_name,
        "patient_code": pat.patient_code,
        "services": ", ".join(it.service_name_snapshot for it in inv.items[:3]) +
                    ("\u2026" if len(inv.items) > 3 else ""),
        "invoice_amount": float(inv.grand_total),
        "paid_amount": float(p.amount),
        "method": method_names.get(p.method, p.method.title()),
        "staff": staff_names.get(p.received_by_id, "\u2014"),
    } for p, inv, pat in rows]

    return render_template("admin/finreports/daily_collection.html",
                           day=day, entries=entries, total=total,
                           by_method=by_method)
