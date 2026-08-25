"""File upload validation & secure storage for prescriptions/reports.

Supports local storage and Cloudflare R2 (toggle with USE_CLOUD_STORAGE=1).
"""
import os
import uuid
from pathlib import Path

from flask import abort
from PIL import Image
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}

# Subfolders under UPLOAD_FOLDER
FOLDER_PRESCRIPTIONS = "prescriptions"
FOLDER_REPORTS = "reports"
FOLDER_INVOICES = "invoices"
FOLDER_BANNERS = "banners"


class UploadError(ValueError):
    pass


def _extension_allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _verify_content(file_storage) -> str:
    """Read magic bytes to confirm the real type; returns extension."""
    pos = file_storage.tell()
    head = file_storage.read(16)
    file_storage.seek(pos)
    if not head:
        raise UploadError("Empty file.")
    if head.startswith(b"%PDF"):
        return "pdf"
    # Images via Pillow (validates structure too)
    try:
        pos = file_storage.tell()
        img = Image.open(file_storage)
        fmt = (img.format or "").lower()
        file_storage.seek(pos)
        if fmt in {"jpeg", "jpg"}:
            return "jpg"
        if fmt == "png":
            return "png"
    except Exception:
        file_storage.seek(pos)
    raise UploadError("Only PDF, JPG, JPEG or PNG files are allowed.")


def save_upload(file_storage, folder: str, max_bytes=None) -> tuple[str, str]:
    """Validate and store an upload with a randomized name.

    Returns (stored_relative_path, original_filename).
    Raises UploadError on invalid files.
    
    When R2 is enabled (USE_CLOUD_STORAGE=1), uploads to R2.
    Otherwise saves to local UPLOAD_FOLDER.
    """
    from flask import current_app

    if file_storage is None or not getattr(file_storage, "filename", ""):
        raise UploadError("No file selected.")
    original = secure_filename(file_storage.filename)
    if not _extension_allowed(original):
        raise UploadError("Allowed types: PDF, JPG, JPEG, PNG.")

    limit = max_bytes or current_app.config["UPLOAD_MAX_BYTES"]
    data = file_storage.read(limit + 1)
    if len(data) > limit:
        raise UploadError("File exceeds the 5 MB size limit.")
    file_storage.seek(0)

    ext = _verify_content(file_storage)
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    relative_path = f"{folder}/{stored_name}"

    # Check if using Cloudflare R2
    use_r2 = _bool(current_app.config.get("USE_CLOUD_STORAGE", "0"))
    if use_r2:
        # Upload to R2
        from app.utils.storage import upload_to_storage
        content_type = {
            "pdf": "application/pdf",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
        }.get(ext, "application/octet-stream")
        file_storage.seek(0)
        uploaded_path, _ = upload_to_storage(file_storage, relative_path, content_type)
        return uploaded_path, original
    else:
        # Local storage
        upload_root = Path(current_app.config["UPLOAD_FOLDER"])
        target_dir = upload_root / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / stored_name
        file_storage.save(str(path))
        os.chmod(str(path), 0o640)
        return relative_path, original


def safe_upload_path(relative_path: str):
    """Resolve a stored relative path under UPLOAD_FOLDER, blocking traversal.
    
    When R2 is enabled, returns a URL instead of a local path.
    """
    from flask import current_app

    use_r2 = _bool(current_app.config.get("USE_CLOUD_STORAGE", "0"))
    if use_r2:
        # Return R2 URL
        from app.utils.storage import get_file_url
        return get_file_url(relative_path)

    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target = (root / relative_path).resolve()
    if root not in target.parents and target != root:
        abort(404)
    return target


def delete_upload(relative_path: str) -> bool:
    try:
        use_r2 = _bool(current_app.config.get("USE_CLOUD_STORAGE", "0"))
        if use_r2:
            from app.utils.storage import delete_from_storage
            return delete_from_storage(relative_path)
        
        # Local storage
        root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
        target = (root / relative_path).resolve()
        if root in target.parents and target.is_file():
            target.unlink()
            return True
    except Exception:
        pass
    return False


def _bool(val):
    return str(val or "0").strip().lower() in {"1", "true", "yes", "on"}
