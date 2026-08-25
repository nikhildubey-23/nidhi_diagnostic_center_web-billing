"""Admin settings: business info, website content, FAQs, banners."""
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import (
    BooleanField, IntegerField, StringField, TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.extensions import db
from app.models.content import Banner, FAQ, WebsiteContent
from app.utils.files import FOLDER_BANNERS, UploadError, delete_upload, save_upload
from app.utils.helpers import all_settings, log_audit, permission_required, set_setting

settings_bp = Blueprint("settings", __name__)

BUSINESS_KEYS = [
    ("center_name", "Centre Name"),
    ("tagline", "Tagline"),
    ("address_line1", "Address Line 1"),
    ("address_line2", "Address Line 2"),
    ("phone", "Phone"),
    ("phone_secondary", "Phone (secondary)"),
    ("whatsapp", "WhatsApp Number"),
    ("email", "Email"),
    ("gst_number", "GSTIN (optional)"),
    ("invoice_prefix", "Invoice Prefix"),
    ("patient_prefix", "Patient ID Prefix"),
    ("booking_prefix", "Booking Prefix"),
]

CONTENT_KEYS = [
    ("opening_hours_weekday", "Opening Hours (Weekday)"),
    ("opening_hours_sunday", "Opening Hours (Sunday)"),
    ("invoice_footer", "Invoice Footer Message"),
    ("invoice_terms", "Invoice Terms & Conditions"),
    ("map_embed_url", "Google Maps Embed URL"),
    ("map_link_url", "Google Maps Link URL"),
]


@settings_bp.route("/")
@login_required
@permission_required("settings.manage")
def index():
    data = all_settings()
    return render_template("admin/settings/business.html", data=data,
                           business_keys=BUSINESS_KEYS, content_keys=CONTENT_KEYS)


@settings_bp.route("/save", methods=["POST"])
@login_required
@permission_required("settings.manage")
def save():
    allowed = {k for k, _ in BUSINESS_KEYS} | {k for k, _ in CONTENT_KEYS} | {
        "home_hero_title", "about_intro", "about_mission", "why_choose_us",
        "show_service_prices_public",
    }
    changed = 0
    for key in request.form:
        if key not in allowed:
            continue
        set_setting(key, request.form.get(key, "").strip(), updated_by=current_user.id)
        changed += 1
    # checkbox special-case
    if "show_service_prices_public" not in request.form:
        set_setting("show_service_prices_public", "", updated_by=current_user.id)
    log_audit("settings_updated", "setting", None, {"keys": changed})
    db.session.commit()
    flash(f"{changed or 0} settings saved.", "success")
    return redirect(url_for(".index"))


# ---------------- Website content ----------------

@settings_bp.route("/content", methods=["GET", "POST"])
@login_required
@permission_required("settings.manage")
def content():
    form = ContentForm()
    if form.validate_on_submit():
        row = WebsiteContent(
            key=form.key.data.strip(),
            title=form.title.data.strip() if form.title.data else "",
            body=form.body.data.strip() if form.body.data else "",
            is_active=form.is_active.data,
            created_by_id=current_user.id,
            updated_by_id=current_user.id,
        )
        db.session.add(row)
        log_audit("website_content_created", "website_content", row.id,
                  {"key": row.key})
        db.session.commit()
        flash(f"Content '{row.key}' created.", "success")
        return redirect(url_for(".content"))

    rows = WebsiteContent.query.order_by(WebsiteContent.key).all()
    from app.utils.helpers import get_setting
    return render_template("admin/settings/content.html", rows=rows,
                           show_public_prices=get_setting("show_service_prices_public"))


class ContentForm(FlaskForm):
    title = StringField(validators=[Optional(), Length(max=200)])
    body = TextAreaField(validators=[Length(max=5000)])


@settings_bp.route("/content/<int:row_id>", methods=["GET", "POST"])
@login_required
@permission_required("settings.manage")
def edit_content(row_id):
    row = db.get_or_404(WebsiteContent, row_id)
    form = ContentForm(obj=row)
    if form.validate_on_submit():
        form.populate_obj(row)
        row.updated_by_id = current_user.id
        log_audit("website_content_updated", "website_content", row.id,
                  {"key": row.key})
        db.session.commit()
        flash(f"Content '{row.key}' updated.", "success")
        return redirect(url_for(".content"))
    return render_template("admin/settings/content_form.html", form=form, row=row)


# ---------------- FAQs ----------------

class FAQForm(FlaskForm):
    question = StringField(validators=[DataRequired(), Length(max=250)])
    answer = TextAreaField(validators=[DataRequired(), Length(max=3000)])
    sort_order = IntegerField(validators=[NumberRange(0, 999)])
    is_active = BooleanField(default=True)


@settings_bp.route("/faqs")
@login_required
@permission_required("settings.manage")
def faqs():
    rows = FAQ.query.order_by(FAQ.sort_order).all()
    return render_template("admin/settings/faqs.html", rows=rows)


@settings_bp.route("/faqs/new", methods=["GET", "POST"])
@login_required
@permission_required("settings.manage")
def new_faq():
    form = FAQForm()
    if form.validate_on_submit():
        faq = FAQ(question=form.question.data.strip(),
                  answer=form.answer.data.strip(),
                  sort_order=form.sort_order.data or 0,
                  is_active=form.is_active.data)
        db.session.add(faq)
        log_audit("faq_created", "faq", None, {"q": faq.question[:80]})
        db.session.commit()
        flash("FAQ added.", "success")
        return redirect(url_for(".faqs"))
    return render_template("admin/settings/faq_form.html", form=form, is_edit=False)


@settings_bp.route("/faqs/<int:faq_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("settings.manage")
def edit_faq(faq_id):
    faq = db.get_or_404(FAQ, faq_id)
    form = FAQForm(obj=faq)
    if form.validate_on_submit():
        form.populate_obj(faq)
        log_audit("faq_updated", "faq", faq.id)
        db.session.commit()
        flash("FAQ updated.", "success")
        return redirect(url_for(".faqs"))
    return render_template("admin/settings/faq_form.html", form=form, is_edit=True)


@settings_bp.route("/faqs/<int:faq_id>/delete", methods=["POST"])
@login_required
@permission_required("settings.manage")
def delete_faq(faq_id):
    faq = db.get_or_404(FAQ, faq_id)
    db.session.delete(faq)
    log_audit("faq_deleted", "faq", faq_id)
    db.session.commit()
    flash("FAQ deleted.", "success")
    return redirect(url_for(".faqs"))


# ---------------- Banners ----------------

class BannerForm(FlaskForm):
    headline = StringField(validators=[DataRequired(), Length(max=200)])
    subtext = StringField(validators=[Optional(), Length(max=300)])
    link_url = StringField(validators=[Optional(), Length(max=255)])
    sort_order = IntegerField(validators=[NumberRange(0, 999)])
    is_active = BooleanField(default=True)


@settings_bp.route("/banners")
@login_required
@permission_required("settings.manage")
def banners():
    rows = Banner.query.order_by(Banner.sort_order).all()
    return render_template("admin/settings/banners.html", rows=rows)


@settings_bp.route("/banners/new", methods=["GET", "POST"])
@login_required
@permission_required("settings.manage")
def new_banner():
    form = BannerForm()
    if form.validate_on_submit():
        banner = Banner(headline=form.headline.data.strip(),
                        subtext=(form.subtext.data or "").strip() or None,
                        link_url=(form.link_url.data or "").strip() or None,
                        sort_order=form.sort_order.data or 0,
                        is_active=form.is_active.data)
        file = request.files.get("image")
        try:
            if file and file.filename:
                rel, orig = save_upload(file, FOLDER_BANNERS)
                banner.image_path = rel
        except UploadError as exc:
            flash(str(exc), "danger")
            return render_template("admin/settings/banner_form.html",
                                   form=form, is_edit=False)
        db.session.add(banner)
        db.session.flush()
        log_audit("banner_created", "banner", banner.id)
        db.session.commit()
        flash("Banner created.", "success")
        return redirect(url_for(".banners"))
    return render_template("admin/settings/banner_form.html", form=form, is_edit=False)


@settings_bp.route("/banners/<int:banner_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("settings.manage")
def edit_banner(banner_id):
    banner = db.get_or_404(Banner, banner_id)
    form = BannerForm(obj=banner)
    if form.validate_on_submit():
        form.populate_obj(banner)
        file = request.files.get("image")
        try:
            if file and file.filename:
                rel, orig = save_upload(file, FOLDER_BANNERS)
                delete_upload(banner.image_path or "")
                banner.image_path = rel
        except UploadError as exc:
            flash(str(exc), "danger")
            return render_template("admin/settings/banner_form.html",
                                   form=form, is_edit=True, banner=banner)
        log_audit("banner_updated", "banner", banner.id)
        db.session.commit()
        flash("Banner updated.", "success")
        return redirect(url_for(".banners"))
    return render_template("admin/settings/banner_form.html", form=form,
                           is_edit=True, banner=banner)


@settings_bp.route("/banners/<int:banner_id>/delete", methods=["POST"])
@login_required
@permission_required("settings.manage")
def delete_banner(banner_id):
    banner = db.get_or_404(Banner, banner_id)
    delete_upload(banner.image_path or "")
    db.session.delete(banner)
    log_audit("banner_deleted", "banner", banner_id)
    db.session.commit()
    flash("Banner deleted.", "success")
    return redirect(url_for(".banners"))
