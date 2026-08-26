"""Public website routes."""
import logging
import re as _re
from datetime import date, datetime

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request,
    url_for,
)
from flask_wtf import FlaskForm
from markupsafe import Markup
from wtforms import (
    DateField, EmailField, FileField, IntegerField, RadioField,
    SelectField, StringField, TextAreaField, TimeField,
)
from wtforms.validators import (
    DataRequired, Email, Length, NumberRange, Optional, Regexp,
)

from app.extensions import db, limiter
from app.models.booking import Booking
from app.models.content import Banner, FAQ
from app.models.service import Service, ServiceCategory
from app.services.notifications import notify_booking_received
from app.utils.files import FOLDER_PRESCRIPTIONS, UploadError, save_upload
from app.utils.helpers import log_audit, show_public_prices
from app.utils.numbering import next_booking_code

log = logging.getLogger(__name__)

website_bp = Blueprint("website", __name__)


def _active_categories():
    return (
        ServiceCategory.query.filter_by(is_active=True)
        .order_by(ServiceCategory.sort_order, ServiceCategory.name)
        .all()
    )


class BookingForm(FlaskForm):
    patient_name = StringField("Full Name", validators=[DataRequired(), Length(2, 128)])
    mobile = StringField(
        "Mobile Number",
        validators=[DataRequired(), Regexp(r"^[6-9]\d{9}$", message="Enter a valid 10-digit Indian mobile number.")],
    )
    email = EmailField("Email (optional)", validators=[Optional(), Email(), Length(max=254)])
    age = IntegerField("Age", validators=[Optional(), NumberRange(min=0, max=120)])
    gender = SelectField(
        "Gender", choices=[("", "Select"), ("male", "Male"), ("female", "Female"), ("other", "Other")],
        validators=[DataRequired()],
    )
    service_id = SelectField("Service / Test", coerce=int, validators=[DataRequired()])
    preferred_date = DateField("Preferred Date", validators=[DataRequired()])
    preferred_time = SelectField(
        "Preferred Time",
        choices=[
            ("", "Any / First available"),
            ("08:00", "8:00 AM"), ("09:00", "9:00 AM"), ("10:00", "10:00 AM"),
            ("11:00", "11:00 AM"), ("12:00", "12:00 PM"), ("16:00", "4:00 PM"),
            ("17:00", "5:00 PM"), ("18:00", "6:00 PM"), ("19:00", "7:00 PM"),
            ("20:00", "8:00 PM"),
        ],
        default="",
    )
    technician_preference = StringField("Doctor/Technician preference (optional)", validators=[Optional(), Length(max=128)])
    address = TextAreaField("Address (optional)", validators=[Optional(), Length(max=500)])
    notes = TextAreaField("Notes (optional)", validators=[Optional(), Length(max=1000)])
    prescription = FileField("Upload prescription/referral (PDF/JPG/PNG)", validators=[Optional()])

    def validate_preferred_date(self, field):
        if field.data and field.data < date.today():
            raise ValueError("Preferred date cannot be in the past.")

    def validate_prescription(self, field):
        if field.data and field.data.filename:
            filename = field.data.filename.lower()
            if not filename.endswith((".pdf", ".jpg", ".jpeg", ".png")):
                raise ValueError("Prescription must be PDF, JPG or PNG.")


@website_bp.route("/")
def home():
    cats = _active_categories()
    banners = Banner.query.filter_by(is_active=True).order_by(Banner.sort_order).limit(3).all()
    faqs = FAQ.query.filter_by(is_active=True).order_by(FAQ.sort_order).all()
    content = {}
    from app.models.content import WebsiteContent
    for row in WebsiteContent.query.all():
        content[row.key] = row
    form = BookingForm()
    form.service_id.choices = [(0, "-- Select a test --")] + [
        (s.id, s.name) for s in Service.query.filter_by(is_active=True).order_by(Service.name)
    ]
    return render_template(
        "website/home.html", categories=cats, banners=banners, faqs=faqs,
        content=content, form=form, show_prices=show_public_prices(),
        today=date.today(),
    )


@website_bp.route("/about")
def about():
    from app.models.content import WebsiteContent
    content = {row.key: row for row in WebsiteContent.query.all()}
    return render_template("website/about.html", content=content)


@website_bp.route("/services")
def services():
    cats = _active_categories()
    show_prices = show_public_prices()
    return render_template("website/services.html", categories=cats, show_prices=show_prices)


@website_bp.route("/services/<slug>")
def category(slug):
    cat = ServiceCategory.query.filter_by(slug=slug, is_active=True).first_or_404()
    show_prices = show_public_prices()
    others = [c for c in _active_categories() if c.id != cat.id][:4]
    return render_template("website/category.html", category=cat,
                           show_prices=show_prices, others=others)


@website_bp.route("/contact")
def contact():
    form = BookingForm()  # reused only to read csrf token shape; contact uses simple POST below
    return render_template("website/contact.html")


class ContactMessage:
    pass


@website_bp.route("/book", methods=["GET", "POST"])
@limiter.limit("8 per hour", methods=["POST"])
def book():
    preselect = request.args.get("service", type=int)
    form = BookingForm()
    active_services = Service.query.filter_by(is_active=True).order_by(Service.name).all()
    form.service_id.choices = [(0, "-- Select a test --")] + [(s.id, s.name) for s in active_services]

    if request.method == "GET" and preselect:
        form.service_id.data = preselect if any(s.id == preselect for s in active_services) else 0

    if form.validate_on_submit():
        svc = db.session.get(Service, form.service_id.data)
        if svc is None or not svc.is_active:
            flash("Please choose a valid service/test.", "danger")
            return render_template("website/book.html", form=form, services=active_services)
        else:
            booking = Booking(
                patient_name=form.patient_name.data.strip(),
                mobile=form.mobile.data.strip(),
                email=(form.email.data or "").strip() or None,
                age=form.age.data,
                gender=form.gender.data or None,
                address=(form.address.data or "").strip() or None,
                notes=(form.notes.data or "").strip() or None,
                technician_preference=(form.technician_preference.data or "").strip() or None,
                service_id=svc.id,
                preferred_date=form.preferred_date.data,
                status="pending",
                source="website",
            )
            t = form.preferred_time.data
            if t:
                booking.preferred_time = datetime.strptime(t, "%H:%M").time()

            if form.prescription.data and form.prescription.data.filename:
                try:
                    rel, orig = save_upload(form.prescription.data, FOLDER_PRESCRIPTIONS)
                    booking.prescription_file = rel
                    booking.prescription_original_name = orig
                except (UploadError, ValueError):
                    flash("Prescription file rejected. Please upload PDF/JPG/PNG under 5 MB.", "danger")
                    return render_template("website/book.html", form=form,
                                           services=active_services, today=date.today())

            booking.booking_code = next_booking_code()
            db.session.add(booking)
            db.session.flush()
            notify_booking_received(booking)
            try:
                from app.services.notifications import deliver_pending
                deliver_pending(limit=5)
            except Exception:
                current_app.logger.exception("Notification delivery failed")
            log_audit("booking_created", "booking", booking.id,
                      {"code": booking.booking_code, "source": "website"})
            db.session.commit()
            return redirect(url_for("website.book_success", code=booking.booking_code))

    return render_template("website/book.html", form=form, services=active_services,
                           today=date.today())


@website_bp.route("/book/quick", methods=["POST"])
@limiter.limit("8 per hour", methods=["POST"])
def book_quick():
    """Handle the Quick Appointment Request from the home page hero."""
    patient_name = (request.form.get("patient_name") or "").strip()
    mobile = (request.form.get("mobile") or "").strip()
    service_id = request.form.get("service_id", type=int)
    preferred_date_raw = (request.form.get("preferred_date") or "").strip()
    preferred_time = (request.form.get("preferred_time") or "").strip()

    if not patient_name or len(patient_name) < 2:
        flash("Please enter your full name.", "danger")
        return redirect(url_for("website.home"))
    if not mobile or not _re.match(r"^[6-9]\d{9}$", mobile):
        flash("Please enter a valid 10-digit Indian mobile number.", "danger")
        return redirect(url_for("website.home"))
    if not service_id:
        flash("Please choose a test/service.", "danger")
        return redirect(url_for("website.home"))

    svc = db.session.get(Service, service_id)
    if svc is None or not svc.is_active:
        flash("Please choose a valid service/test.", "danger")
        return redirect(url_for("website.home"))

    try:
        pref_date = date.fromisoformat(preferred_date_raw)
    except (ValueError, TypeError):
        flash("Please enter a valid preferred date.", "danger")
        return redirect(url_for("website.home"))

    if pref_date < date.today():
        flash("Preferred date cannot be in the past.", "danger")
        return redirect(url_for("website.home"))

    booking = Booking(
        patient_name=patient_name,
        mobile=mobile,
        service_id=svc.id,
        preferred_date=pref_date,
        status="pending",
        source="website",
    )
    if preferred_time:
        try:
            booking.preferred_time = datetime.strptime(preferred_time, "%H:%M").time()
        except ValueError:
            pass

    booking.booking_code = next_booking_code()
    db.session.add(booking)
    db.session.flush()
    notify_booking_received(booking)
    try:
        from app.services.notifications import deliver_pending
        deliver_pending(limit=5)
    except Exception:
        current_app.logger.exception("Notification delivery failed")
    log_audit("booking_created", "booking", booking.id,
              {"code": booking.booking_code, "source": "website"})
    db.session.commit()
    return redirect(url_for("website.book_success", code=booking.booking_code))


@website_bp.route("/book/success/<code>")
def book_success(code):
    booking = Booking.query.filter_by(booking_code=code).first_or_404()
    return render_template("website/book_success.html", booking=booking)


@website_bp.route("/book/status", methods=["GET", "POST"])
def book_status():
    """Patient checks a booking reference."""
    code = request.values.get("code", "").strip().upper()
    booking = None
    if code:
        booking = Booking.query.filter(
            Booking.booking_code.ilike(code)
        ).first()
        if booking is None:
            flash("No booking found for that reference number.", "warning")
    return render_template("website/book_status.html", booking=booking, code=code)


# --- simple contact form ---------------------------------------------------
class ContactForm(FlaskForm):
    name = StringField(validators=[DataRequired(), Length(2, 120)])
    email = EmailField(validators=[Optional(), Email()])
    phone = StringField(validators=[DataRequired(), Regexp(r"^[\d\s+-]{7,15}$")])
    message = TextAreaField(validators=[DataRequired(), Length(5, 2000)])


@website_bp.route("/contact/submit", methods=["POST"])
@limiter.limit("6 per hour", methods=["POST"])
def contact_submit():
    form = ContactForm()
    if form.validate_on_submit():
        from app.services.notifications import queue_notification, deliver_pending
        from app.utils.helpers import get_setting
        body = f"Name: {form.name.data}\nPhone: {form.phone.data}\nEmail: {form.email.data or '-'}\n\n{form.message.data}"
        queue_notification("email", get_setting("email", ""),
                           subject=f"Website enquiry from {form.name.data}",
                           body=body, related_type="enquiry")
        try:
            deliver_pending(limit=3)
        except Exception:
            current_app.logger.exception("Contact notification failed")
        flash("Thank you! Your message has been received. We will get back to you soon.", "success")
    else:
        flash("Please fill all required fields correctly.", "danger")
    return redirect(url_for("website.contact") + "#contact-form")
