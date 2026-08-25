"""Website content management models (editable from admin panel)."""
from app.extensions import db
from app.models.user import TimestampMixin


class WebsiteContent(db.Model, TimestampMixin):
    """Key/value content blocks for public pages (hero text, about us...)."""
    __tablename__ = "website_contents"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    title = db.Column(db.String(200))  # human label in admin UI
    body = db.Column(db.Text, default="")
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))


class FAQ(db.Model, TimestampMixin):
    __tablename__ = "faqs"

    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(255), nullable=False)
    answer = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


class Banner(db.Model, TimestampMixin):
    __tablename__ = "banners"

    id = db.Column(db.Integer, primary_key=True)
    headline = db.Column(db.String(200), nullable=False)
    subtext = db.Column(db.String(300))
    image_path = db.Column(db.String(255))
    link_url = db.Column(db.String(255))
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
