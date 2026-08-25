"""Admin authentication."""
import logging

from flask import (
    Blueprint, current_app, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, Length, Regexp

from app.extensions import db, limiter
from app.models.user import User
from app.utils.helpers import log_audit

log = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, template_folder="../templates")


class LoginForm(FlaskForm):
    username = StringField(
        "Username", validators=[
            DataRequired(), Length(max=64),
            Regexp(r"^[\w.@-]+$", message="Invalid characters in username."),
        ]
    )
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin_dash.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter(
            User.username == form.username.data.strip()
        ).first()
        if user is None or not user.check_password(form.password.data):
            log.warning("Failed login attempt username=%s ip=%s",
                        form.username.data, request.remote_addr)
            flash("Invalid username or password.", "danger")
        elif not user.is_active:
            flash("This account has been deactivated.", "danger")
        else:
            login_user(user, remember=False)
            user.last_login_at = db.session.query(db.func.now()).scalar()
            db.session.commit()
            log_audit("login", "user", user.id)
            db.session.commit()
            next_url = request.args.get("next")
            if next_url and not next_url.startswith("/"):
                next_url = None
            return redirect(next_url or url_for("admin_dash.dashboard"))
    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["POST", "GET"])
@login_required
def logout():
    log_audit("logout", "user", current_user.id)
    db.session.commit()
    logout_user()
    return redirect(url_for("auth.login"))
