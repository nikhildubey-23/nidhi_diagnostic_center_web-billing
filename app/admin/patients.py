"""Admin patient management."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from flask_wtf import FlaskForm
from sqlalchemy import or_
from wtforms import (
    DateField, EmailField, IntegerField, RadioField, StringField, TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Regexp

from app.extensions import db
from app.models.booking import Booking
from app.models.billing import Invoice
from app.models.patient import Patient
from app.models.report import DiagnosticReport
from app.utils.helpers import log_audit, permission_required
from app.utils.numbering import next_patient_code

patients_bp = Blueprint("patients", __name__)


class PatientForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(2, 128)])
    mobile = StringField("Mobile", validators=[DataRequired(), Regexp(r"^[6-9]\d{9}$")])
    email = EmailField("Email", validators=[Optional(), Length(max=254)])
    date_of_birth = DateField("Date of Birth", validators=[Optional()])
    age = IntegerField("Age (if DOB unknown)", validators=[Optional(), NumberRange(0, 120)])
    gender = RadioField(
        "Gender", choices=[("male", "Male"), ("female", "Female"), ("other", "Other")],
        validators=[DataRequired()],
    )
    address = TextAreaField("Address", validators=[Optional(), Length(max=500)])
    emergency_contact = StringField(
        "Emergency Contact", validators=[Optional(), Length(max=20)]
    )
    medical_notes = TextAreaField(
        "Medical Notes (allergies, history...)",
        validators=[Optional(), Length(max=2000)],
    )


@patients_bp.route("/")
@login_required
@permission_required("patients.manage")
def index():
    page = request.args.get("page", 1, type=int)
    q = (request.args.get("q") or "").strip()
    query = Patient.query.filter_by(is_active=True)
    if q:
        like = f"%{q}%"
        code_like = like.replace("%", "") + "%"
        query = query.filter(or_(
            Patient.full_name.ilike(like),
            Patient.mobile.ilike(like),
            Patient.email.ilike(like),
            Patient.patient_code.ilike(code_like),
        ))
    pagination = query.order_by(Patient.created_at.desc()).paginate(page=page, per_page=20)
    return render_template("admin/patients/index.html", pagination=pagination, q=q)


@patients_bp.route("/new", methods=["GET", "POST"])
@login_required
@permission_required("patients.manage")
def create():
    form = PatientForm()
    if form.validate_on_submit():
        patient = Patient(patient_code=next_patient_code())
        form.populate_obj(patient)
        db.session.add(patient)
        db.session.flush()
        log_audit("patient_created", "patient", patient.id,
                  {"code": patient.patient_code})
        db.session.commit()
        flash(f"Patient {patient.full_name} registered as {patient.patient_code}.",
              "success")
        return redirect(url_for(".profile", patient_id=patient.id))
    return render_template("admin/patients/form.html", form=form, patient=None)


@patients_bp.route("/<int:patient_id>")
@login_required
@permission_required("patients.manage")
def profile(patient_id):
    patient = db.get_or_404(Patient, patient_id)
    bookings = Booking.query.filter_by(patient_id=patient.id).order_by(
        Booking.created_at.desc()).limit(20).all()
    invoices = Invoice.query.filter_by(patient_id=patient.id).order_by(
        Invoice.created_at.desc()).limit(20).all()
    reports = DiagnosticReport.query.filter_by(patient_id=patient.id).order_by(
        DiagnosticReport.created_at.desc()).limit(20).all()
    return render_template("admin/patients/profile.html", patient=patient,
                           bookings=bookings, invoices=invoices, reports=reports)


@patients_bp.route("/<int:patient_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("patients.manage")
def edit(patient_id):
    patient = db.get_or_404(Patient, patient_id)
    form = PatientForm(obj=patient)
    if form.validate_on_submit():
        form.populate_obj(patient)
        log_audit("patient_updated", "patient", patient.id,
                  {"code": patient.patient_code})
        db.session.commit()
        flash("Patient updated.", "success")
        return redirect(url_for(".profile", patient_id=patient.id))
    return render_template("admin/patients/form.html", form=form, patient=patient)


@patients_bp.route("/<int:patient_id>/deactivate", methods=["POST"])
@login_required
@permission_required("patients.manage")
def deactivate(patient_id):
    patient = db.get_or_404(Patient, patient_id)
    patient.is_active = not patient.is_active
    log_audit("patient_deactivated" if not patient.is_active else "patient_activated",
              "patient", patient.id, {"code": patient.patient_code})
    db.session.commit()
    flash(f"Patient {'deactivated' if not patient.is_active else 'reactivated'}.", "success")
    return redirect(url_for(".index"))
