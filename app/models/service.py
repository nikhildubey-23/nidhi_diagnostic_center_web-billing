"""Diagnostic services & categories (managed from admin panel)."""
from app.extensions import db
from app.models.user import TimestampMixin


class ServiceCategory(db.Model, TimestampMixin):
    __tablename__ = "service_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(96), unique=True, nullable=False)
    slug = db.Column(db.String(96), unique=True, nullable=False, index=True)
    icon = db.Column(db.String(64))  # inline svg key / emoji
    description = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    services = db.relationship(
        "Service", back_populates="category", lazy="dynamic",
        order_by="Service.name",
    )

    def __repr__(self):  # pragma: no cover
        return f"<ServiceCategory {self.name}>"


class Service(db.Model, TimestampMixin):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False, index=True)
    category_id = db.Column(
        db.Integer, db.ForeignKey("service_categories.id"), nullable=False
    )
    description = db.Column(db.Text)
    preparation_instructions = db.Column(db.Text)
    duration_minutes = db.Column(db.Integer, default=30)
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    show_price_public = db.Column(db.Boolean, default=True, nullable=False)
    discount_eligible = db.Column(db.Boolean, default=True, nullable=False)
    tax_percent = db.Column(db.Numeric(5, 2), default=0, nullable=False)
    requires_appointment = db.Column(db.Boolean, default=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    category = db.relationship("ServiceCategory", back_populates="services")

    bookings = db.relationship(
        "BookingService", back_populates="service", lazy="dynamic"
    )

    @property
    def price_display(self):
        return float(self.price or 0)

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "price": self.price_display,
            "tax_percent": float(self.tax_percent or 0),
            "discount_eligible": self.discount_eligible,
            "category": self.category.name if self.category else "",
        }

    def __repr__(self):  # pragma: no cover
        return f"<Service {self.code} {self.name}>"
