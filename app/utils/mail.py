"""Gmail SMTP mail utility for sending notifications."""
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from flask import current_app


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str = None,
    cc: str = None,
    bcc: str = None,
) -> bool:
    """
    Send email via Gmail SMTP (supports both TLS and SSL).
    
    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_body: HTML email body
        text_body: Plain text fallback (optional)
        cc: CC recipients (optional)
        bcc: BCC recipients (optional)
    
    Returns:
        bool: True if sent successfully, False otherwise
    """
    smtp_server = current_app.config.get("MAIL_SERVER", "smtp.gmail.com")
    smtp_port = int(current_app.config.get("MAIL_PORT", "465"))
    use_tls = current_app.config.get("MAIL_USE_TLS", "1") in ("1", "true", "yes")
    username = current_app.config.get("MAIL_USERNAME", "")
    password = current_app.config.get("MAIL_PASSWORD", "")
    default_sender = current_app.config.get("MAIL_DEFAULT_SENDER", "")

    if not username or not password:
        current_app.logger.warning("SMTP credentials not configured")
        return False

    # Build message
    msg = MIMEMultipart("alternative")
    msg["From"] = default_sender or username
    msg["To"] = to_email
    msg["Subject"] = subject

    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc

    # Add text body
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))

    # Add HTML body
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        
        # Use SSL (port 465) or STARTTLS (port 587)
        if smtp_port == 465:
            # Direct SSL connection
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context, timeout=30) as server:
                server.login(username, password)
                _send(server, msg, to_email, cc, bcc)
        else:
            # STARTTLS connection
            with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
                if use_tls:
                    server.starttls(context=context)
                server.login(username, password)
                _send(server, msg, to_email, cc, bcc)
            
        current_app.logger.info(f"Email sent to {to_email}: {subject}")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        current_app.logger.error(f"SMTP authentication failed: {e}")
        return False
    except smtplib.SMTPException as e:
        current_app.logger.error(f"SMTP error: {e}")
        return False
    except Exception as e:
        current_app.logger.error(f"Email send failed: {e}")
        return False


def _send(server, msg, to_email, cc=None, bcc=None):
    """Helper to send email via server."""
    recipients = [to_email]
    if cc:
        recipients.extend([r.strip() for r in cc.split(",")])
    if bcc:
        recipients.extend([r.strip() for r in bcc.split(",")])
    
    server.sendmail(msg["From"], recipients, msg.as_string())


def test_smtp_connection() -> dict:
    """
    Test SMTP connection and return status.
    
    Returns:
        dict: {"success": bool, "message": str}
    """
    smtp_server = current_app.config.get("MAIL_SERVER", "smtp.gmail.com")
    smtp_port = int(current_app.config.get("MAIL_PORT", "465"))
    use_tls = current_app.config.get("MAIL_USE_TLS", "1") in ("1", "true", "yes")
    username = current_app.config.get("MAIL_USERNAME", "")
    password = current_app.config.get("MAIL_PASSWORD", "")

    if not username or not password:
        return {"success": False, "message": "SMTP credentials not configured"}

    try:
        context = ssl.create_default_context()
        
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context, timeout=10) as server:
                server.login(username, password)
        else:
            with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
                if use_tls:
                    server.starttls(context=context)
                server.login(username, password)
            
        return {
            "success": True,
            "message": f"Connected to {smtp_server}:{smtp_port}"
        }
        
    except smtplib.SMTPAuthenticationError:
        return {
            "success": False,
            "message": "Authentication failed - check username and app password"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}"
        }
