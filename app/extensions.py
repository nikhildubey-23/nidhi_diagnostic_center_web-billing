"""Flask extension instances (single import point to avoid cycles)."""
import os
from pathlib import Path
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)

login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"


def _normalize_redis_url(url: str) -> str:
    """Upstash URLs must use rediss:// for TLS. Ensure correct scheme."""
    if not url:
        return ""
    if url.startswith("redis://") and "upstash" in url:
        return url.replace("redis://", "rediss://", 1)
    return url


def _get_redis_client(app):
    """Create a Redis client from Upstash credentials for Flask-Session."""
    url = app.config.get("UPSTASH_REDIS_URL", "")
    if not url:
        return None
    url = _normalize_redis_url(url)
    try:
        import redis
        return redis.from_url(url, decode_responses=True)
    except Exception as e:
        app.logger.warning(f"Redis connection failed: {e}")
        return None


def init_session(app):
    """Configure Flask-Session with Redis or filesystem fallback."""
    # Vercel serverless: skip file-based sessions entirely
    if os.environ.get("VERCEL"):
        app.logger.info("Flask-Session: Skipping (Vercel serverless)")
        return

    session_type = app.config.get("SESSION_TYPE", "filesystem")

    if session_type == "redis":
        r = _get_redis_client(app)
        if r is not None:
            try:
                from flask_session import Session
                app.config["SESSION_REDIS"] = r
                Session(app)
                app.logger.info("Flask-Session: Using Redis")
                return
            except Exception as e:
                app.logger.warning(f"Redis session init failed: {e}")

    # Fallback: try filesystem sessions; skip if read-only
    app.config["SESSION_TYPE"] = "filesystem"
    upload_folder = app.config.get("UPLOAD_FOLDER", "uploads")
    app.config["SESSION_FILE_DIR"] = os.path.join(upload_folder, "sessions")
    try:
        session_dir = Path(app.config["SESSION_FILE_DIR"])
        session_dir.mkdir(parents=True, exist_ok=True)
        test_file = session_dir / ".write_test"
        test_file.write_text("")
        test_file.unlink()
        from flask_session import Session
        Session(app)
        app.logger.info("Flask-Session: Using filesystem")
    except OSError:
        app.logger.warning("Flask-Session: Read-only filesystem, skipping file sessions")
    except Exception:
        pass


def init_rate_limiter(app):
    """Configure rate limiter — memory on Vercel, Redis elsewhere."""
    # Vercel serverless: always use memory (no persistent Redis connection)
    if os.environ.get("VERCEL"):
        app.config["RATELIMIT_STORAGE_URI"] = "memory://"
        app.logger.info("Rate limiter: Using memory (Vercel)")
        return

    # Non-Vercel: try Redis if configured
    storage_uri = app.config.get("RATELIMIT_STORAGE_URI", "memory://")
    if storage_uri != "memory://":
        r = _get_redis_client(app)
        if r is not None:
            try:
                r.ping()
                app.config["RATELIMIT_STORAGE_URI"] = storage_uri
                app.logger.info("Rate limiter: Using Redis")
                return
            except Exception as e:
                app.logger.warning(f"Rate limiter Redis failed: {e}, falling back to memory")

    app.config["RATELIMIT_STORAGE_URI"] = "memory://"
    app.logger.info("Rate limiter: Using memory")
