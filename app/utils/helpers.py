"""Shared helpers: settings store, money formatting, dates, audit."""
import json
from datetime import date, datetime, timezone
from functools import wraps

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user

from app.extensions import db

# ---------------------------------------------------------------------------
# Business settings (key/value with defaults)
# ---------------------------------------------------------------------------

SETTING_DEFAULTS = {
    "center_name": "Nidhi Diagnostic",
    "tagline": "Advanced Diagnostics \u00b7 Trusted Care",
    "address_line1": "Sarkanda",
    "address_line2": "Bilaspur, Chhattisgarh 495001",
    "phone": "+91 90000 00000",
    "phone_secondary": "",
    "whatsapp": "+91 90000 00000",
    "email": "contact@nidhidiagnostic.in",
    "gst_number": "",
    "invoice_prefix": "NID-INV",
    "patient_prefix": "NID-P",
    "booking_prefix": "NID-BK",
    "invoice_footer": "Thank you for choosing Nidhi Diagnostic. Please retain this "
                      "invoice for your records. Reports are usually ready within "
                      "24 hours; you will be called when your report is ready.",
    "invoice_terms": "1. Fees once paid are non-refundable. "
                     "2. Please carry your previous medical records if any. "
                     "3. This is a computer generated invoice.",
    "opening_hours_weekday": "Monday \u2013 Saturday: 7:30 AM \u2013 9:00 PM",
    "opening_hours_sunday": "Sunday: 8:00 AM \u2013 2:00 PM",
    "map_embed_url": "https://www.google.com/maps?q=Sarkanda,+Bilaspur,+Chhattisgarh&output=embed",
    "map_link_url": "https://www.google.com/maps/search/?api=1&query=Sarkanda%2C+Bilaspur%2C+Chhattisgarh",
    "show_service_prices_public": "1",
}


class Setting(db.Model):
    __tablename__ = "settings"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text, nullable=False, default="")
    updated_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    def __repr__(self):  # pragma: no cover
        return f"<Setting {self.key}>"


def get_setting(key, default=""):
    row = db.session.get(Setting, key)
    if row is not None:
        return row.value
    return SETTING_DEFAULTS.get(key, default)


def set_setting(key, value, updated_by=None):
    row = db.session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=str(value), updated_by=updated_by)
        db.session.add(row)
    else:
        row.value = str(value)
        row.updated_by = updated_by
    return row


def all_settings():
    """Return merged dict of defaults + stored settings."""
    data = dict(SETTING_DEFAULTS)
    for row in Setting.query.all():
        data[row.key] = row.value
    return data


def show_public_prices() -> bool:
    return get_setting("show_service_prices_public", "0") in {"1", "true", "True"}


# ---------------------------------------------------------------------------
# Money / formatting helpers (templates)
# ---------------------------------------------------------------------------

def inr(amount) -> str:
    """Format a Decimal/number as Indian Rupees with grouping, e.g. ₹3,600.00"""
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        amount = 0.0
    s = f"{amount:,.2f}"
    return f"\u20b9{s}"


def fmt_date(d):
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, date):
        return d.strftime("%d/%m/%Y")
    return ""


def fmt_datetime(dt):
    if isinstance(dt, datetime):
        return dt.strftime("%d/%m/%Y, %I:%M %p")
    return ""


def parse_date_safe(value, *formats):
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except (TypeError, ValueError):
            continue
    return None


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

def log_audit(action, entity_type="", entity_id=None, details=None):
    """Record an administrative action. Never raises into request flow."""
    from app.models.audit import AuditLog

    try:
        user_id = None
        try:
            from flask_login import current_user
            if current_user.is_authenticated:
                user_id = current_user.id
        except Exception:
            pass
        entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=json.dumps(details, default=str) if details else None,
            ip_address=request.remote_addr if request else None,
        )
        db.session.add(entry)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Authorization decorators
# ---------------------------------------------------------------------------

def permission_required(*permissions):
    """Allow access only to users whose role grants ANY of the given
    permissions. Super admins bypass everything."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.url))
            if not current_user.has_permission(*permissions):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def roles_required(*role_names):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.url))
            role = getattr(current_user, "role_name", "")
            if role != "super_admin" and role not in role_names:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
