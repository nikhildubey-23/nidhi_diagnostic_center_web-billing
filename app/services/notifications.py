"""Notification service abstraction.

Queues notifications in the DB and attempts delivery via configured
providers. Email uses Gmail SMTP; WhatsApp is a pluggable interface.
"""
import logging
from datetime import datetime, timezone

from app.extensions import db
from app.models.notification import Notification

log = logging.getLogger(__name__)


def queue_notification(channel, recipient, subject, body,
                       related_type=None, related_id=None):
    """Queue a notification for delivery."""
    if not recipient:
        return None
    n = Notification(
        channel=channel, recipient=recipient, subject=subject or "",
        body=body, related_type=related_type, related_id=related_id,
    )
    db.session.add(n)
    return n


def deliver_pending(limit=20):
    """Attempt delivery of queued notifications via SMTP."""
    from flask import current_app

    sent = failed = 0
    pending = (Notification.query
               .filter_by(status="pending")
               .order_by(Notification.created_at)
               .limit(limit).all())
    
    for n in pending:
        if n.channel == "email" and n.recipient:
            try:
                from app.utils.mail import send_email
                ok = send_email(
                    to_email=n.recipient,
                    subject=n.subject or "",
                    html_body=_wrap_html(n.subject or "", n.body or ""),
                    text_body=n.body,
                )
            except Exception as exc:
                log.exception("Email delivery error")
                n.status = "failed"
                n.error = str(exc)[:480]
                failed += 1
                continue
            
            if ok:
                n.status = "sent"
                n.sent_at = datetime.now(timezone.utc).replace(tzinfo=None)
                sent += 1
            else:
                n.status = "failed"
                n.error = "SMTP send failed"
                failed += 1
        else:
            n.status = "skipped"
            sent += 1  # Don't block on non-email channels
    
    db.session.commit()
    return {"sent": sent, "failed": failed, "queued": len(pending) - sent - failed}


def _wrap_html(title, text_body):
    """Wrap text body in a professional HTML email template."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #6d371f; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
            .content {{ padding: 20px; border: 1px solid #ddd; border-top: none; border-radius: 0 0 8px 8px; }}
            .footer {{ text-align: center; padding: 15px; font-size: 12px; color: #666; margin-top: 20px; }}
            .btn {{ display: inline-block; background: #6d371f; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2 style="margin:0;">Nidhi Diagnostic</h2>
            <p style="margin:5px 0 0 0; font-size: 14px; opacity: 0.9;">Sarkanda, Bilaspur, Chhattisgarh</p>
        </div>
        <div class="content">
            <h3>{title}</h3>
            <p>{text_body.replace(chr(10), '<br>')}</p>
        </div>
        <div class="footer">
            <p>Nidhi Diagnostic &bull; Sarkanda, Bilaspur, C.G.</p>
            <p>Phone: +91 90000 00000 | Email: contact@nidhidiagnostic.in</p>
        </div>
    </body>
    </html>
    """


# ---------------------------------------------------------------------------
# High-level helpers used by booking/billing flows
# ---------------------------------------------------------------------------

def notify_booking_received(booking):
    """Send booking confirmation email to patient."""
    queue_notification(
        "email", booking.email or "",
        subject=f"Booking Received - {booking.booking_code}",
        body=(f"Dear {booking.patient_name},\n\n"
              f"Thank you for booking with Nidhi Diagnostic!\n\n"
              f"Booking Reference: {booking.booking_code}\n"
              f"Service: {booking.service.name}\n"
              f"Preferred Date: {booking.preferred_date}\n"
              f"Time: {booking.preferred_time.strftime('%I:%M %p') if booking.preferred_time else 'Any available slot'}\n\n"
              f"Your booking is pending confirmation. Our team will call you shortly to confirm your appointment.\n\n"
              f"Thank you,\nNidhi Diagnostic"),
        related_type="booking", related_id=booking.id,
    )


def notify_invoice_created(invoice):
    """Send invoice email to patient."""
    from app.utils.helpers import inr
    queue_notification(
        "email", invoice.patient.email or "",
        subject=f"Invoice {invoice.invoice_code} - Nidhi Diagnostic",
        body=(f"Dear {invoice.patient.full_name},\n\n"
              f"Your invoice has been generated.\n\n"
              f"Invoice Number: {invoice.invoice_code}\n"
              f"Amount: {inr(invoice.grand_total)}\n"
              f"Balance Due: {inr(invoice.balance_due)}\n\n"
              f"Thank you for choosing Nidhi Diagnostic.\n\n"
              f"Nidhi Diagnostic\n"
              f"Sarkanda, Bilaspur, C.G."),
        related_type="invoice", related_id=invoice.id,
    )


def notify_report_ready(report):
    """Send report ready notification to patient."""
    queue_notification(
        "email", report.patient.email or "",
        subject=f"Report Ready - {report.title}",
        body=(f"Dear {report.patient.full_name},\n\n"
              f"Your diagnostic report is ready for collection.\n\n"
              f"Report: {report.title}\n"
              f"Report Date: {report.report_date.strftime('%d %b %Y')}\n\n"
              f"Please collect your report from Nidhi Diagnostic or contact us for digital copy.\n\n"
              f"Thank you,\nNidhi Diagnostic"),
        related_type="report", related_id=report.id,
    )


def notify_payment_received(invoice, amount, method):
    """Send payment receipt to patient."""
    from app.utils.helpers import inr
    queue_notification(
        "email", invoice.patient.email or "",
        subject=f"Payment Receipt - {invoice.invoice_code}",
        body=(f"Dear {invoice.patient.full_name},\n\n"
              f"We have received your payment.\n\n"
              f"Invoice: {invoice.invoice_code}\n"
              f"Amount Paid: {inr(amount)}\n"
              f"Payment Method: {method.title()}\n"
              f"Balance Due: {inr(invoice.balance_due)}\n\n"
              f"Thank you for your payment.\n\n"
              f"Nidhi Diagnostic"),
        related_type="payment", related_id=invoice.id,
    )
