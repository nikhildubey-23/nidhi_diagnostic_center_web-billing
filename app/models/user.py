"""Users, roles and permissions."""
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class Permission(db.Model):
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255))

    roles = db.relationship(
        "Role", secondary="role_permissions", back_populates="permissions"
    )

    # Canonical permission codes
    DASHBOARD = "dashboard.view"
    BOOKINGS = "bookings.manage"
    PATIENTS = "patients.manage"
    SERVICES = "services.manage"
    BILLING = "billing.manage"
    PAYMENTS = "payments.manage"
    REPORTS = "reports.manage"
    FINREPORTS = "finreports.view"
    USERS = "users.manage"
    SETTINGS = "settings.manage"
    AUDIT = "audit.view"


ROLE_PERMISSIONS = {
    "super_admin": [
        "dashboard.view", "bookings.manage", "patients.manage", "services.manage",
        "billing.manage", "payments.manage", "reports.manage", "finreports.view",
        "users.manage", "settings.manage", "audit.view",
    ],
    "admin": [        "dashboard.view", "bookings.manage", "patients.manage", "services.manage",
        "billing.manage", "payments.manage", "reports.manage", "finreports.view",
        "audit.view",
    ],
    "billing_staff": [
        "dashboard.view", "patients.manage", "billing.manage",
        "payments.manage", "finreports.view",
    ],
    "receptionist": [
        "dashboard.view", "bookings.manage", "patients.manage",
        "billing.manage", "payments.manage",
    ],
    "technician": [
        "dashboard.view", "bookings.manage", "patients.manage", "reports.manage",
    ],
}


ROLE_LABELS = {
    "super_admin": "Super Admin",
    "admin": "Admin",
    "billing_staff": "Billing Staff",
    "receptionist": "Receptionist",
    "technician": "Technician",
}


role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False, index=True)
    label = db.Column(db.String(64))
    permissions = db.relationship(
        "Permission", secondary="role_permissions", back_populates="roles",
        lazy="selectin",
    )

    @property
    def codes(self):
        return {p.code for p in self.permissions}


class User(db.Model, TimestampMixin, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(254), unique=True)
    full_name = db.Column(db.String(128), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_login_at = db.Column(db.DateTime)

    role = db.relationship("Role", lazy="selectin")

    @property
    def role_name(self):
        return self.role.name if self.role else ""

    def set_password(self, password: str):
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def has_permission(self, *codes) -> bool:
        """True if the user's role grants ANY of `codes` (super_admin bypasses)."""
        if not self.role:
            return False
        if self.role.name == "super_admin":
            return True
        return bool(set(codes) & self.role.codes)

    # Flask-Login integration
    @property
    def is_authenticated_user(self):
        return self.is_active

    def get_id(self):
        return str(self.id)

    def __repr__(self):  # pragma: no cover
        return f"<User {self.username} ({self.role_name})>"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
