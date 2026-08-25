"""Bookings raised from the public website or by staff."""
from datetime import datetime, timezone

from sqlalchemy import Index

from app.extensions import db
from app.models.user import TimestampMixin

BOOKING_STATUSES = [
    ("pending", "Pending"),
    ("confirmed", "Confirmed"),
    ("arrived", "Arrived"),
    ("in_progress", "In Progress"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
    ("no_show", "No Show"),
]
STATUS_VALUES = [s[0] for s in BOOKING_STATUSES]


class Booking(db.Model, TimestampMixin):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    booking_code = db.Column(db.String(40), unique=True, nullable=False, index=True)

    # Linked patient once registered (may be NULL while pending)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"))

    # Snapshot of requester details from the public form
    patient_name = db.Column(db.String(128), nullable=False)
    mobile = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(254))
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    address = db.Column(db.Text)
    notes = db.Column(db.Text)
    technician_preference = db.Column(db.String(128))
    prescription_file = db.Column(db.String(255))  # randomized stored name
    prescription_original_name = db.Column(db.String(255))

    service_id = db.Column(
        db.Integer, db.ForeignKey("services.id"), nullable=False
    )
    preferred_date = db.Column(db.Date, nullable=False)
    preferred_time = db.Column(db.Time)

    status = db.Column(db.String(20), default="pending", nullable=False, index=True)
    source = db.Column(db.String(20), default="website")  # website/admin/walk_in

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    confirmed_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    cancel_reason = db.Column(db.String(255))

    patient = db.relationship("Patient", back_populates="bookings", foreign_keys=[patient_id])
    service = db.relationship("Service")
    created_by = db.relationship("User")
    services = db.relationship(
        "BookingService", back_populates="booking",
        cascade="all, delete-orphan", lazy="selectin",
    )
    invoices = db.relationship("Invoice", back_populates="booking", lazy="dynamic")

    __table_args__ = (
        Index("ix_bookings_date_status", "preferred_date", "status"),
        Index("ix_bookings_mobile", "mobile"),
    )

    @property
    def status_label(self):
        return dict(BOOKING_STATUSES).get(self.status, self.status.title())

    def transition_allowed(self, new_status) -> bool:
        allowed = {
            "pending": {"confirmed", "cancelled", "no_show"},
            "confirmed": {"arrived", "cancelled", "no_show", "in_progress"},
            "arrived": {"in_progress", "completed", "cancelled"},
            "in_progress": {"completed", "cancelled"},
            "completed": set(),
            "cancelled": set(),
            "no_show": {"confirmed"},
        }
        return new_status in allowed.get(self.status, set())

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.booking_code,
            "name": self.patient_name,
            "mobile": self.mobile,
            "service": self.service.name if self.service else "",
            "date": self.preferred_date.isoformat() if self.preferred_date else None,
            "time": self.preferred_time.strftime("%H:%M") if self.preferred_time else None,
            "status": self.status,
            "status_label": self.status_label,
        }

    def __repr__(self):  # pragma: no cover
        return f"<Booking {self.booking_code} {self.status}>"


class BookingService(db.Model, TimestampMixin):
    """Services attached to a booking (primary + any added by admin)."""
    __tablename__ = "booking_services"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(
        db.Integer, db.ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False
    )
    service_id = db.Column(
        db.Integer, db.ForeignKey("services.id"), nullable=False
    )
    price_snapshot = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)

    booking = db.relationship("Booking", back_populates="services")
    service = db.relationship("Service", back_populates="bookings")
