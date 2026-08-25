"""DiagnosticReport model: uploaded patient test reports."""
import os

from app.extensions import db
from app.models.user import TimestampMixin


class DiagnosticReport(db.Model, TimestampMixin):
    __tablename__ = "diagnostic_reports"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    patient_id = db.Column(
        db.Integer, db.ForeignKey("patients.id"), nullable=False, index=True
    )
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"))
    invoice_item_id = db.Column(db.Integer, db.ForeignKey("invoice_items.id", ondelete="SET NULL"))
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"))

    doctor_name = db.Column(db.String(128))  # reporting doctor / radiologist
    report_date = db.Column(db.Date, nullable=False)
    file_path = db.Column(db.String(255), nullable=False)  # relative to UPLOAD_FOLDER
    file_original_name = db.Column(db.String(255))
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default="draft")  # draft/completed
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    patient = db.relationship("Patient", back_populates="reports")
    service = db.relationship("Service")
    booking = db.relationship("Booking")
    uploaded_by = db.relationship("User")

    @property
    def filename(self):
        return os.path.basename(self.file_path or "")

    @property
    def status_label(self):
        return "Completed" if self.status == "completed" else "Draft"

    def __repr__(self):  # pragma: no cover
        return f"<DiagnosticReport {self.id} {self.title}>"
