"""Audit trail for administrative/billing actions."""
from app.extensions import db
from app.models.user import TimestampMixin


class AuditLog(db.Model, TimestampMixin):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    action = db.Column(db.String(64), nullable=False, index=True)
    entity_type = db.Column(db.String(40), index=True)
    entity_id = db.Column(db.String(40), index=True)
    details = db.Column(db.Text)  # JSON string
    ip_address = db.Column(db.String(64))

    user = db.relationship("User")

    def describe(self):
        return f"{self.action} {self.entity_type or ''} {self.entity_id or ''}".strip()
