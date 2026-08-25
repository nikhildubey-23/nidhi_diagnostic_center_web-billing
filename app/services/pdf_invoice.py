"""PDF invoice generation using ReportLab (landscape A4, print-friendly)."""
from io import BytesIO
from pathlib import Path

from flask import send_file
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)


def generate_invoice_pdf(invoice) -> BytesIO:
    from app.utils.helpers import all_settings, get_setting, inr, fmt_date

    buf = BytesIO()
    page_w, page_h = landscape(A4)
    left_margin = right_margin = 1.5 * cm
    top_margin = bottom_margin = 1.2 * cm

    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=left_margin, rightMargin=right_margin,
        topMargin=top_margin, bottomMargin=bottom_margin,
    )

    styles = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, leading=12)
    small = ParagraphStyle("Small", parent=body, fontSize=7.5, leading=9)
    title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=16, spaceAfter=2)
    heading = ParagraphStyle("Head", parent=styles["Heading3"], fontSize=11, spaceAfter=4)
    center = ParagraphStyle("Center", parent=body, alignment=1)
    right = ParagraphStyle("Right", parent=body, alignment=2)
    bold = ParagraphStyle("Bold", parent=body, fontName="Helvetica-Bold")

    story = []
    s = all_settings()
    story.append(Paragraph(f"<b>{s.get('center_name', 'Nidhi Diagnostic')}</b>", title_style))
    story.append(Paragraph(s.get("address_line1", ""), body))
    story.append(Paragraph(s.get("address_line2", ""), body))
    story.append(Paragraph(
        f"Phone: {s.get('phone', '')} &nbsp;|&nbsp; Email: {s.get('email', '')}", body
    ))
    gst = s.get("gst_number", "")
    if gst:
        story.append(Paragraph(f"GSTIN: {gst}", body))
    story.append(Spacer(1, 6))

    patient = invoice.patient
    story.append(Paragraph("Patient Details", heading))
    story.append(Paragraph(
        f"<b>{patient.patient_code} &nbsp;&mdash; {patient.full_name}</b><br/>"
        f"Age: {patient.display_age} &nbsp; Gender: {patient.gender or '\u2014'}<br/>"
        f"Mobile: {patient.mobile}<br/>"
        f"Address: {patient.address or '\u2014'}<br/>"
        , body,
    ))
    story.append(Spacer(1, 6))

    payment_method = invoice.payment_method_display or "\u2014"
    story.append(Paragraph(
        f"<b>Invoice No:</b> {invoice.invoice_code} &nbsp;&nbsp; "
        f"<b>Date:</b> {fmt_date(invoice.finalized_at or invoice.created_at)} &nbsp;&nbsp; "
        f"<b>Status:</b> {invoice.status_label}<br/>"
        + (f"<b>Payment Method:</b> {payment_method}" if invoice.status != "draft" else ""),
        body,
    ))
    story.append(Spacer(1, 8))

    # Services table
    data = [["#", "Service", "Qty", "Rate", "Discount", "Tax %", "Amount"]]
    for idx, item in enumerate(invoice.items, 1):
        data.append([
            idx,
            item.service_name_snapshot,
            item.qty,
            inr(item.rate),
            inr(item.discount_amount),
            f"{item.tax_percent}%",
            inr(item.line_total),
        ])
    data.append(["", "", "", "", "", "Subtotal", inr(invoice.subtotal)])
    if float(invoice.discount_amount or 0) > 0:
        data.append(["", "", "", "", "", "Discount", f"\u2212 {inr(invoice.discount_amount)}"])
    if float(invoice.tax_total or 0) > 0:
        data.append(["", "", "", "", "", "Tax", inr(invoice.tax_total)])
    if float(invoice.other_charges or 0) > 0:
        data.append(["", "", "", "", "", "Other Charges", inr(invoice.other_charges)])
    data.append(["", "", "", "", "", "Grand Total", inr(invoice.grand_total)])
    data.append(["", "", "", "", "", "Paid", inr(invoice.amount_paid)])
    data.append(["", "", "", "", "", "Balance Due", inr(invoice.balance_due)])

    col_widths = [30, None, 30, 70, 70, 50, 80]
    col_widths[1] = page_w - left_margin - right_margin - sum(
        c for c in col_widths if c is not None
    )
    t = Table(data, colWidths=[c for c in col_widths])
    num_rows = len(data)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("GRID", (0, 0), (-1, 0), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, num_rows - 4), [colors.white, colors.HexColor("#f0f9ff")]),
        ("FONTNAME", (4, num_rows - 4), (-1, -1), "Helvetica-Bold"),
        ("LINEBELOW", (0, num_rows - 4), (-1, num_rows - 4), 1, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    footer = s.get("invoice_footer", "")
    terms = s.get("invoice_terms", "")
    if terms:
        story.append(Paragraph(f"<b>Terms &amp; Conditions:</b><br/>{terms}", small))
        story.append(Spacer(1, 6))
    if footer:
        story.append(Paragraph(footer, small))
    story.append(Spacer(1, 16))
    story.append(Paragraph("Authorized Signature ___________________________", body))

    doc.build(story)
    buf.seek(0)
    return buf


def send_invoice_pdf(invoice) -> send_file:
    from app.utils.helpers import get_setting

    buf = generate_invoice_pdf(invoice)
    fname = f"{invoice.invoice_code}.pdf"
    return send_file(
        buf, mimetype="application/pdf", as_attachment=True,
        download_name=fname,
    )
