"""Admin: manage service categories and services."""
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from flask_wtf import FlaskForm
from sqlalchemy import or_
from wtforms import BooleanField, IntegerField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, Regexp

from app.extensions import db
from app.models.service import Service, ServiceCategory
from app.utils.helpers import log_audit, permission_required
import re as _re


def _slugify(s):
    return _re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


services_bp = Blueprint("services", __name__)


class CategoryForm(FlaskForm):
    name = StringField("Category Name", validators=[DataRequired(), Length(2, 80)])
    icon = StringField("Icon / Emoji", validators=[Optional(), Length(max=32)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=2000)])
    is_active = BooleanField("Active", default=True)
    sort_order = IntegerField("Sort Order", default=0, validators=[NumberRange(0, 999)])


class ServiceForm(FlaskForm):
    code = StringField("Service Code", validators=[DataRequired(), Length(2, 20),
                                                   Regexp(r"^[A-Z0-9-]+$", message="Capital letters, digits, hyphens only.")])
    name = StringField("Service Name", validators=[DataRequired(), Length(2, 128)])
    category_id = SelectField("Category", coerce=int, validators=[DataRequired()])
    description = TextAreaField("Description", validators=[Optional(), Length(max=2000)])
    preparation_instructions = TextAreaField("Preparation Instructions", validators=[Optional(), Length(max=2000)])
    duration_minutes = IntegerField("Duration (minutes)", default=30, validators=[NumberRange(0, 480)])
    price = StringField("Price (\u20b9)", validators=[DataRequired(), Length(max=12)])
    tax_percent = StringField("Tax %", validators=[Optional(), Length(max=8)])
    show_price_public = BooleanField("Show Price on Website", default=True)
    discount_eligible = BooleanField("Discount Eligible", default=True)
    requires_appointment = BooleanField("Requires Appointment", default=True)
    is_active = BooleanField("Active", default=True)


def _load_service_rows():
    from app.models.service import ServiceCategory as Cat
    cats = Cat.query.order_by(Cat.sort_order, Cat.name).all()
    out = []
    for c in cats:
        rows = (Service.query.filter_by(category_id=c.id)
                .order_by(Service.name).all())
        out.append((c, rows))
    return out


# ---------- Categories ----------
@services_bp.route("/")
@login_required
@permission_required("services.manage")
def index():
    rows = _load_service_rows()
    return render_template("admin/services/index.html", category_rows=rows)


@services_bp.route("/category/new", methods=["GET", "POST"])
@login_required
@permission_required("services.manage")
def new_category():
    form = CategoryForm()
    if form.validate_on_submit():
        cat = ServiceCategory(name=form.name.data.strip(),
                              slug=_slugify(form.name.data))
        form.populate_obj(cat)
        db.session.add(cat)
        log_audit("category_created", "service_category", None,
                  {"name": cat.name, "slug": cat.slug})
        db.session.commit()
        flash(f"Category '{cat.name}' created.", "success")
        return redirect(url_for(".index"))
    return render_template("admin/services/category_form.html", form=form, is_edit=False)


@services_bp.route("/category/<int:cat_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("services.manage")
def edit_category(cat_id):
    cat = db.get_or_404(ServiceCategory, cat_id)
    form = CategoryForm(obj=cat)
    if form.validate_on_submit():
        old_slug = cat.slug
        form.populate_obj(cat)
        cat.slug = _slugify(cat.name)
        log_audit("category_updated", "service_category", cat.id,
                  {"old_slug": old_slug, "new_slug": cat.slug})
        db.session.commit()
        flash("Category updated.", "success")
        return redirect(url_for(".index"))
    return render_template("admin/services/category_form.html", form=form, is_edit=True, cat=cat)


# ---------- Services ----------
@services_bp.route("/new", methods=["GET", "POST"])
@login_required
@permission_required("services.manage")
def new_service():
    form = ServiceForm()
    form.category_id.choices = [(c.id, c.name) for c in ServiceCategory.query.order_by(ServiceCategory.name).all()]
    if form.validate_on_submit():
        svc = Service()
        form.populate_obj(svc)
        svc.price = Decimal(form.price.data)
        svc.tax_percent = Decimal(form.tax_percent.data or "0")
        db.session.add(svc)
        log_audit("service_created", "service", None,
                  {"code": svc.code, "name": svc.name})
        db.session.commit()
        flash(f"Service '{svc.name}' created.", "success")
        return redirect(url_for(".index"))
    return render_template("admin/services/form.html", form=form, is_edit=False)


@services_bp.route("/<int:svc_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("services.manage")
def edit_service(svc_id):
    svc = db.get_or_404(Service, svc_id)
    form = ServiceForm(obj=svc, price=str(svc.price), tax_percent=str(svc.tax_percent or 0))
    form.category_id.choices = [(c.id, c.name) for c in ServiceCategory.query.order_by(ServiceCategory.name).all()]
    if form.validate_on_submit():
        form.populate_obj(svc)
        svc.price = Decimal(form.price.data)
        svc.tax_percent = Decimal(form.tax_percent.data or "0")
        log_audit("service_updated", "service", svc.id,
                  {"code": svc.code, "name": svc.name})
        db.session.commit()
        flash("Service updated.", "success")
        return redirect(url_for(".index"))
    return render_template("admin/services/form.html", form=form, is_edit=True, service=svc)


@services_bp.route("/<int:svc_id>/toggle", methods=["POST"])
@login_required
@permission_required("services.manage")
def toggle_service(svc_id):
    svc = db.get_or_404(Service, svc_id)
    svc.is_active = not svc.is_active
    log_audit("service_toggled", "service", svc.id,
              {"code": svc.code, "active": svc.is_active})
    db.session.commit()
    flash(f"Service {svc.code} {'activated' if svc.is_active else 'deactivated'}.", "success")
    return redirect(url_for(".index"))
