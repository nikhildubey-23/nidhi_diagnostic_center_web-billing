"""Nidhi Diagnostic — application factory."""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from app.config import BASE_DIR, config_by_name


def _configure_logging(app: Flask):
    log_dir = Path(BASE_DIR) / "logs"
    log_dir.mkdir(exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s :: %(message)s"
    )
    file_handler = RotatingFileHandler(
        log_dir / "app.log", maxBytes=2_000_000, backupCount=5
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.INFO)

    root = app.logger
    root.setLevel(logging.DEBUG if app.debug else logging.INFO)
    if not root.handlers:
        root.addHandler(file_handler)
    if app.config.get("TESTING"):
        root.setLevel(logging.WARNING)


def create_app(config_name: str | None = None) -> Flask:
    config_name = config_name or os.environ.get("FLASK_CONFIG", "production")
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_by_name[config_name])
    _configure_logging(app)

    # -- extensions -------------------------------------------------------
    from app.extensions import db, csrf, login_manager, limiter, migrate, init_session

    db.init_app(app)
    migrate.init_app(app, db, compare_type=True)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    init_session(app)

    from app import models as _models  # noqa: F401  (register models with SQLAlchemy)

    # -- template helpers --------------------------------------------------
    from app.utils.helpers import (
        all_settings, fmt_date, fmt_datetime, get_setting, inr,
    )

    app.jinja_env.globals.update(
        get_setting=get_setting,
        settings=lambda: {**all_settings()},
        inr=inr,
        fmt_date=fmt_date,
        fmt_datetime=fmt_datetime,
        center_name=lambda: get_setting("center_name", "Nidhi Diagnostic"),
    )
    app.jinja_env.filters["inr"] = inr
    app.jinja_env.filters["fmt_date"] = fmt_date
    app.jinja_env.filters["fmt_datetime"] = fmt_datetime

    @app.context_processor
    def inject_globals():
        from flask_login import current_user  # noqa
        return {
            "current_year": __import__("datetime").date.today().year,
            "nav_settings": {
                "phone": get_setting("phone"),
                "email": get_setting("email"),
                "whatsapp": get_setting("whatsapp"),
                "address_line1": get_setting("address_line1"),
                "address_line2": get_setting("address_line2"),
                "opening_hours_weekday": get_setting("opening_hours_weekday"),
                "opening_hours_sunday": get_setting("opening_hours_sunday"),
            },
        }

    # -- security headers ---------------------------------------------------
    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if not app.debug:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    # -- blueprints ---------------------------------------------------------
    from app.auth.routes import auth_bp
    from app.website.routes import website_bp
    from app.admin.dashboard import admin_dash_bp
    from app.admin.bookings import bookings_bp
    from app.admin.patients import patients_bp
    from app.admin.services import services_bp
    from app.admin.billing import billing_bp
    from app.admin.invoices import invoices_bp
    from app.admin.payments import payments_bp
    from app.admin.reports import reports_bp
    from app.admin.finreports import finreports_bp
    from app.admin.settings import settings_bp
    from app.admin.users import users_bp
    from app.admin.audit import audit_bp
    from app.api.routes import api_bp

    app.register_blueprint(website_bp)
    app.register_blueprint(auth_bp, url_prefix="/admin/auth")
    app.register_blueprint(admin_dash_bp, url_prefix="/admin")
    app.register_blueprint(bookings_bp, url_prefix="/admin/bookings")
    app.register_blueprint(patients_bp, url_prefix="/admin/patients")
    app.register_blueprint(services_bp, url_prefix="/admin/services")
    app.register_blueprint(billing_bp, url_prefix="/admin/billing")
    app.register_blueprint(invoices_bp, url_prefix="/admin/invoices")
    app.register_blueprint(payments_bp, url_prefix="/admin/payments")
    app.register_blueprint(reports_bp, url_prefix="/admin/reports")
    app.register_blueprint(finreports_bp, url_prefix="/admin/reports/financial")
    app.register_blueprint(settings_bp, url_prefix="/admin/settings")
    app.register_blueprint(users_bp, url_prefix="/admin/users")
    app.register_blueprint(audit_bp, url_prefix="/admin/audit")
    app.register_blueprint(api_bp, url_prefix="/api/v1")

    # -- error handlers -------------------------------------------------------
    def _error_payload(code, message):
        if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
            return jsonify(error=message), code
        return render_template(f"errors/{code}.html"), code

    @app.errorhandler(403)
    def forbidden(e):
        return _error_payload(403, "You do not have permission to access this resource.")

    @app.errorhandler(404)
    def not_found(e):
        return _error_payload(404, "Page not found.")

    @app.errorhandler(405)
    def method_not_allowed(e):
        return _error_payload(405, "Method not allowed.")

    @app.errorhandler(413)
    def too_large(e):
        return _error_payload(413, "Uploaded file is too large (max 8 MB).")

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Unhandled server error")
        return _error_payload(500, "Something went wrong on our side. Please try again.")

    # -- CLI commands ----------------------------------------------------------
    from app.cli import register_cli
    register_cli(app)

    return app
