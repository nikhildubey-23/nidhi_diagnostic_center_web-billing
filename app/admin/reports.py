"""Admin diagnostic reports: upload, download, replace, complete."""
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy import or_
from wtforms import (
    DateField, FileField, SelectField, StringField, TextAreaField,
)
from wtforms.validators import DataRequired, Length, Optional

from app.extensions import db
from app.models.booking import Booking
from app.models.patient import Patient
from app.models.report import DiagnosticReport
from app.services.notifications import notify_report_ready
from app.utils.files import (
    FOLDER_REPORTS, UploadError, delete_upload, safe_upload_path, save_upload,
)
from app.utils.helpers import log_audit, permission_required

reports_bp = Blueprint("reports", __name__)


class ReportForm(FlaskForm):
    title = StringField("Report Title", validators=[DataRequired(), Length(2, 200)])
    patient_id = SelectField("Patient", coerce=int, validators=[DataRequired()])
    service_id = SelectField("Test / Service", coerce=int)
    booking_id = SelectField("Related Booking", coerce=int)
    doctor_name = StringField("Reporting Doctor / Radiologist", validators=[Optional(), Length(max=128)])
    report_date = DateField("Report Date", validators=[DataRequired()])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=2000)])
    file = FileField("Report File (PDF/JPG/PNG)")


def _choices():
    patients = [(p.id, f"{p.full_name} ({p.patient_code})")
                for p in Patient.query.filter_by(is_active=True).order_by(Patient.full_name)]
    from app.models.service import Service
    services = [("", "\u2014")] + [(s.id, s.name)
                for s in Service.query.filter_by(is_active=True).order_by(Service.name)]
    bookings = [("", "\u2014")] + [
        (b.id, f"{b.booking_code} \u2014 {b.patient_name}")
        for b in Booking.query.order_by(Booking.created_at.desc()).limit(100)]
    return patients, services, bookings


@reports_bp.route("/")
@login_required
@permission_required("reports.manage")
def index():
    page = request.args.get("page", 1, type=int)
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status") or ""
    query = DiagnosticReport.query
    if q:
        like = f"%{q}%"
        query = query.join(Patient).filter(or_(
            DiagnosticReport.title.ilike(like),
            Patient.full_name.ilike(like),
            Patient.patient_code.ilike(f"{q}%"),
        ))
    if status in {"draft", "completed"}:
        query = query.filter(DiagnosticReport.status == status)
    pagination = query.order_by(DiagnosticReport.created_at.desc()).paginate(page=page, per_page=20)
    return render_template("admin/reports/index.html", pagination=pagination,
                           q=q, status=status)


@reports_bp.route("/upload", methods=["GET", "POST"])
@login_required
@permission_required("reports.manage")
def upload():
    form = ReportForm()
    patients, services, bookings = _choices()
    form.patient_id.choices = [(0, "-- select patient --")] + patients
    form.service_id.choices = [(0, "\u2014 none \u2014")] + services[1:]
    form.booking_id.choices = [(0, "\u2014 none \u2014")] + bookings[1:]
    if not form.report_date.data:
        form.report_date.data = date.today()

    # Pre-select patient/booking via query params
    pre_patient = request.args.get("patient_id", type=int)
    pre_booking = request.args.get("booking_id", type=int)
    if request.method == "GET":
        if pre_patient:
            form.patient_id.data = pre_patient
        if pre_booking:
            form.booking_id.data = pre_booking

    if form.validate_on_submit():
        if not form.file.data or not form.file.data.filename:
            flash("Please choose a report file.", "danger")
            return render_template("admin/reports/form.html", form=form, report=None)
        try:
            rel, orig = save_upload(form.file.data, FOLDER_REPORTS)
        except UploadError as exc:
            flash(str(exc), "danger")
            return render_template("admin/reports/form.html", form=form, report=None)

        report = DiagnosticReport(
            title=form.title.data.strip(),
            patient_id=form.patient_id.data,
            service_id=form.service_id.data or None,
            booking_id=form.booking_id.data or None,
            doctor_name=(form.doctor_name.data or "").strip() or None,
            report_date=form.report_date.data,
            notes=(form.notes.data or "").strip() or None,
            file_path=rel,
            file_original_name=orig,
            uploaded_by_id=current_user.id,
        )
        db.session.add(report)
        db.session.flush()
        log_audit("report_uploaded", "report", report.id,
                  {"title": report.title})
        if report.status == "completed":
            notify_report_ready(report)
        db.session.commit()
        flash("Report uploaded.", "success")
        return redirect(url_for(".index"))
    return render_template("admin/reports/form.html", form=form, report=None)


@reports_bp.route("/<int:report_id>")
@login_required
@permission_required("reports.manage")
def detail(report_id):
    report = db.get_or_404(DiagnosticReport, report_id)
    return render_template("admin/reports/detail.html", report=report)


@reports_bp.route("/<int:report_id>/download")
@login_required
@permission_required("reports.manage")
def download(report_id):
    report = db.get_or_404(DiagnosticReport, report_id)
    from flask import send_file
    path = safe_upload_path(report.file_path)
    if not path.is_file():
        flash("Report file missing on server.", "danger")
        return redirect(url_for(".index"))
    ext = path.suffix.lower().lstrip(".")
    mimetype = {"pdf": "application/pdf", "jpg": "image/jpeg",
                "jpeg": "image/jpeg", "png": "image/png"}.get(ext,
                                                             "application/octet-stream")
    return send_file(path, mimetype=mimetype,
                     as_attachment=True,
                     download_name=f"{report.patient.patient_code}_{report.title[:60]}.{ext}")


@reports_bp.route("/<int:report_id>/view")
@login_required
@permission_required("reports.manage")
def view_file(report_id):
    """Inline preview (PDF/image) — still access-controlled."""
    report = db.get_or_404(DiagnosticReport, report_id)
    from flask import send_file
    path = safe_upload_path(report.file_path)
    if not path.is_file():
        flash("Report file missing on server.", "danger")
        return redirect(url_for(".index"))
    ext = path.suffix.lower().lstrip(".")
    mime = {"pdf": "application/pdf", "jpg": "image/jpeg",
            "jpeg": "image/jpeg", "png": "image/png"}.get(ext)
    return send_file(path, mimetype=mime)


@reports_bp.route("/<int:report_id>/complete", methods=["POST"])
@login_required
@permission_required("reports.manage")
def mark_completed(report_id):
    report = db.get_or_404(DiagnosticReport, report_id)
    report.status = "completed"
    log_audit("report_completed", "report", report.id, {"title": report.title})
    notify_report_ready(report)
    try:
        from app.services.notifications import deliver_pending
        deliver_pending(limit=5)
    except Exception:
        pass
    db.session.commit()
    flash("Report marked completed; patient notified if email on file.", "success")
    return redirect(url_for(".detail", report_id=report.id))


@reports_bp.route("/<int:report_id>/replace", methods=["POST"])
@login_required
@permission_required("reports.manage")
def replace_file(report_id):
    report = db.get_or_404(DiagnosticReport, report_id)
    file = request.files.get("file")
    try:
        rel, orig = save_upload(file, FOLDER_REPORTS)
    except (UploadError, ValueError) as exc:
        flash(str(exc), "danger")
        return redirect(url_for(".detail", report_id=report.id))
    delete_upload(report.file_path)
    report.file_path = rel
    report.file_original_name = orig
    log_audit("report_replaced", "report", report.id, {"title": report.title})
    db.session.commit()
    flash("Report file replaced.", "success")
    return redirect(url_for(".detail", report_id=report.id))


@reports_bp.route("/<int:report_id>/delete", methods=["POST"])
@login_required
@permission_required("reports.manage")
def delete(report_id):
    report = db.get_or_404(DiagnosticReport, report_id)
    title = report.title
    delete_upload(report.file_path)
    db.session.delete(report)
    log_audit("report_deleted", "report", report.id, {"title": title})
    db.session.commit()
    flash("Report deleted.", "success")
    return redirect(url_for(".index"))
