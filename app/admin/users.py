"""Admin: staff user management."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, StringField
from wtforms.validators import (
    DataRequired, Email, EqualTo, InputRequired, Length, Optional, Regexp,
)

from app.extensions import db
from app.models.user import ROLE_LABELS, Role, User
from app.utils.helpers import log_audit, permission_required

users_bp = Blueprint("users", __name__)


class UserForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(3, 64),
                                Regexp(r"^[\w.-]+$", message="Letters/digits/._- only.")]
    )
    full_name = StringField("Full Name", validators=[DataRequired(), Length(2, 128)])
    email = StringField("Email", validators=[Optional(), Email(), Length(max=254)])
    role_name = SelectField(
        "Role",
        choices=[(k, v) for k, v in ROLE_LABELS.items() if k != "super_admin"],
        validators=[InputRequired()],
    )
    password = PasswordField(
        "Password (leave blank to keep current)",
        validators=[Optional(), Length(min=8, max=128)],
    )
    confirm = PasswordField(
        "Confirm Password", validators=[EqualTo("password", message="Passwords must match.")]
    )
    is_active = BooleanField("Active", default=True)


@users_bp.route("/")
@login_required
@permission_required("users.manage")
def index():
    users = User.query.order_by(User.username).all()
    return render_template("admin/users/index.html", users=users)


@users_bp.route("/new", methods=["GET", "POST"])
@login_required
@permission_required("users.manage")
def create():
    form = UserForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data.strip()).first():
            flash("Username already exists.", "danger")
            return render_template("admin/users/form.html", form=form, user=None)
        role = Role.query.filter_by(name=form.role_name.data).first()
        user = User(username=form.username.data.strip(),
                    full_name=form.full_name.data.strip(),
                    email=(form.email.data or "").strip() or None,
                    role_id=role.id, is_active=form.is_active.data)
        try:
            if not form.password.data:
                raise ValueError("Password is required for new users.")
            user.set_password(form.password.data)
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("admin/users/form.html", form=form, user=None)
        db.session.add(user)
        db.session.flush()
        log_audit("user_created", "user", user.id,
                  {"username": user.username, "role": role.name})
        db.session.commit()
        flash(f"User '{user.username}' created.", "success")
        return redirect(url_for(".index"))
    return render_template("admin/users/form.html", form=form, user=None)


@users_bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("users.manage")
def edit(user_id):
    user = db.get_or_404(User, user_id)
    form = UserForm(obj=user)
    if request.method == "GET":
        form.role_name.data = user.role.name
        form.password.data = ""
    if form.validate_on_submit():
        dup = User.query.filter(User.username == form.username.data.strip(),
                                User.id != user.id).first()
        if dup:
            flash("Username already exists.", "danger")
            return render_template("admin/users/form.html", form=form, user=user)
        role = Role.query.filter_by(name=form.role_name.data).first()

        # Safety: a super admin cannot demote/deactivate themselves.
        if user.id == current_user.id:
            current_role = user.role.name
            if current_role == "super_admin" and (
                role.name != "super_admin" or not form.is_active.data
            ):
                flash("You cannot demote or deactivate your own account.", "danger")
                return render_template("admin/users/form.html", form=form, user=user)

        old_role = user.role.name
        user.username = form.username.data.strip()
        user.full_name = form.full_name.data.strip()
        user.email = (form.email.data or "").strip() or None
        user.role_id = role.id
        user.is_active = form.is_active.data
        if form.password.data:
            try:
                user.set_password(form.password.data)
            except ValueError as exc:
                flash(str(exc), "danger")
                return render_template("admin/users/form.html", form=form, user=user)
        log_audit("user_updated", "user", user.id,
                  {"username": user.username, "old_role": old_role,
                   "new_role": role.name})
        db.session.commit()
        flash("User updated.", "success")
        return redirect(url_for(".index"))
    return render_template("admin/users/form.html", form=form, user=user)


@users_bp.route("/<int:user_id>/deactivate", methods=["POST"])
@login_required
@permission_required("users.manage")
def toggle(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for(".index"))
    user.is_active = not user.is_active
    log_audit("user_toggled", "user", user.id,
              {"username": user.username, "active": user.is_active})
    db.session.commit()
    flash(f"User {user.username} {'activated' if user.is_active else 'deactivated'}.",
          "success")
    return redirect(url_for(".index"))
