"""Patient model."""
from datetime import datetime, timezone

from sqlalchemy import Index, func

from app.extensions import db
from app.models.user import TimestampMixin


class Patient(db.Model, TimestampMixin):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    patient_code = db.Column(db.String(32), unique=True, index=True, nullable=False)
    full_name = db.Column(db.String(128), nullable=False, index=True)
    mobile = db.Column(db.String(20), nullable=False, index=True)
    email = db.Column(db.String(254))
    date_of_birth = db.Column(db.Date)
    age = db.Column(db.Integer)  # stored; used when DOB unknown
    gender = db.Column(db.String(10))  # male/female/other
    address = db.Column(db.Text)
    emergency_contact = db.Column(db.String(20))
    medical_notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    bookings = db.relationship(
        "Booking", back_populates="patient", lazy="dynamic",
        foreign_keys="Booking.patient_id",
    )
    invoices = db.relationship("Invoice", back_populates="patient", lazy="dynamic")
    reports = db.relationship("DiagnosticReport", back_populates="patient", lazy="dynamic")

    __table_args__ = (
        Index("ix_patients_name_mobile", "full_name", "mobile"),
    )

    @property
    def display_age(self):
        if self.date_of_birth:
            today = datetime.now(timezone.utc).date()
            years = today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
            return f"{years} yrs" if years >= 0 else ""
        if self.age is not None:
            return f"{self.age} yrs"
        return "\u2014"

    @property
    def outstanding(self):
        """Total unpaid balance across finalized invoices."""
        total = (
            db.session.query(func.coalesce(func.sum(Invoice.balance_due), 0))
            .filter(
                Invoice.patient_id == self.id,
                Invoice.status.in_(["finalized", "partially_paid"]),
            )
            .scalar()
        )
        return total or 0

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.patient_code,
            "name": self.full_name,
            "mobile": self.mobile,
            "gender": self.gender or "",
            "age": self.display_age,
        }

    def __repr__(self):  # pragma: no cover
        return f"<Patient {self.patient_code} {self.full_name}>"
