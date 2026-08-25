"""Notification outbox.

Email/WhatsApp providers plug in via NotificationService; rows persist
delivery state so nothing is lost when a provider is not yet configured.
"""
from app.extensions import db
from app.models.user import TimestampMixin


class Notification(db.Model, TimestampMixin):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    channel = db.Column(db.String(20), nullable=False)  # email / whatsapp
    recipient = db.Column(db.String(254), nullable=False)
    subject = db.Column(db.String(200))
    body = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending/sent/failed/skipped
    error = db.Column(db.String(500))
    related_type = db.Column(db.String(40))  # booking / invoice / report
    related_id = db.Column(db.Integer)
    sent_at = db.Column(db.DateTime)
