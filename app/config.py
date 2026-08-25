"""Application configuration."""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(val: str) -> bool:
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-key-change-me")
    SECURITY_PASSWORD_SALT = os.environ.get("SECURITY_PASSWORD_SALT", "dev-insecure-salt-change-me")

    FLASK_ENV = os.environ.get("FLASK_ENV", "production")
    DEBUG = _bool(os.environ.get("FLASK_DEBUG", "0"))

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'nidhi_diagnostic.db'}",
    )
    # Neon PostgreSQL: sslmode=require
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Sessions — Redis (Upstash) in production, filesystem in dev
    SESSION_TYPE = os.environ.get("SESSION_TYPE", "redis")
    UPSTASH_REDIS_URL = os.environ.get("UPSTASH_REDIS_URL", "")
    RATELIMIT_STORAGE_URI = os.environ.get("UPSTASH_REDIS_URL", "")
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = timedelta(hours=12)

    # Rate limiting — memory by default, Redis if UPSTASH_REDIS_URL works
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = "200 per hour"

    # Uploads
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", str(BASE_DIR / "uploads")
    )
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB hard request limit
    ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
    UPLOAD_MAX_BYTES = 5 * 1024 * 1024  # per-file cap for prescriptions/reports

    # Cloudflare R2 storage (optional — falls back to local uploads)
    R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "")  # e.g. https://<account-id>.r2.cloudflarestorage.com
    R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY", "")
    R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY", "")
    R2_BUCKET = os.environ.get("R2_BUCKET", "nidhi-diagnostic")
    R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "")  # e.g. https://pub-xxx.r2.dev
    USE_CLOUD_STORAGE = _bool(os.environ.get("USE_CLOUD_STORAGE", "0"))

    # Business defaults (editable in admin settings, these are fallbacks)
    DEFAULT_CURRENCY = os.environ.get("CURRENCY", "\u20b9")

    # Mail (Gmail SMTP — uses App Password)
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "465"))
    MAIL_USE_TLS = _bool(os.environ.get("MAIL_USE_TLS", "0"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "Nikhil Dubey <snverse27@gmail.com>")

    # WhatsApp (official Business API only — no unofficial automation)
    WHATSAPP_API_URL = os.environ.get("WHATSAPP_API_URL", "")
    WHATSAPP_API_TOKEN = os.environ.get("WHATSAPP_API_TOKEN", "")
    WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "")

    @classmethod
    def init_app(cls, app):
        pass


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    SESSION_TYPE = "filesystem"


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    SERVER_NAME = os.environ.get("SERVER_NAME", "localhost")
    UPLOAD_FOLDER = str(Path(BASE_DIR) / "tests" / "_uploads")
    RATELIMIT_ENABLED = False
    SESSION_TYPE = "filesystem"


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
