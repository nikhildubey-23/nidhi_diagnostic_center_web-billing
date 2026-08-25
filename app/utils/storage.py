"""Cloudflare R2 storage abstraction.

Provides upload_file(), delete_file(), get_url() that work with
both local storage and R2. Toggle with USE_CLOUD_STORAGE=1 env var.
"""
import os
from flask import current_app

# S3-compatible client (lazily initialized)
_r2_client = None


def _get_r2_client():
    """Get or create R2 client (S3-compatible)."""
    global _r2_client
    if _r2_client is not None:
        return _r2_client

    from flask import current_app
    endpoint = current_app.config.get("R2_ENDPOINT", "")
    access_key = current_app.config.get("R2_ACCESS_KEY", "")
    secret_key = current_app.config.get("R2_SECRET_KEY", "")

    if not all([endpoint, access_key, secret_key]):
        return None

    try:
        import boto3
        _r2_client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
        )
        return _r2_client
    except ImportError:
        current_app.logger.warning("boto3 not installed; R2 upload disabled.")
        return None


def _use_cloud_storage():
    """Check if cloud storage is enabled."""
    from flask import current_app
    return _bool(current_app.config.get("USE_CLOUD_STORAGE", "0"))


def _bool(val):
    return str(val or "0").strip().lower() in {"1", "true", "yes", "on"}


def upload_to_storage(file_data, destination_path, content_type=None):
    """Upload file to R2 or local storage.
    
    Args:
        file_data: File-like object or bytes
        destination_path: Relative path (e.g., "prescriptions/abc123.pdf")
        content_type: MIME type (optional, for R2)
    
    Returns:
        tuple: (stored_path, public_url_or_none)
    """
    if not _use_cloud_storage():
        return destination_path, None

    client = _get_r2_client()
    if client is None:
        return destination_path, None

    bucket = current_app.config["R2_BUCKET"]
    public_url = current_app.config.get("R2_PUBLIC_URL", "")

    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type

    try:
        if hasattr(file_data, "read"):
            data = file_data.read()
        else:
            data = file_data

        client.put_object(
            Bucket=bucket,
            Key=destination_path,
            Body=data,
            **extra_args,
        )

        url = f"{public_url.rstrip('/')}/{destination_path}" if public_url else destination_path
        return destination_path, url
    except Exception as e:
        current_app.logger.error(f"R2 upload failed: {e}")
        return destination_path, None


def delete_from_storage(file_path):
    """Delete file from R2."""
    if not _use_cloud_storage():
        return True

    client = _get_r2_client()
    if client is None:
        return True

    bucket = current_app.config["R2_BUCKET"]

    try:
        client.delete_object(Bucket=bucket, Key=file_path)
        return True
    except Exception as e:
        current_app.logger.error(f"R2 delete failed: {e}")
        return False


def get_file_url(file_path, expires_in=3600):
    """Get a presigned URL for R2 file (for private files)."""
    if not _use_cloud_storage():
        return f"/uploads/{file_path}"

    client = _get_r2_client()
    if client is None:
        return f"/uploads/{file_path}"

    bucket = current_app.config["R2_BUCKET"]

    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": file_path},
            ExpiresIn=expires_in,
        )
    except Exception as e:
        current_app.logger.error(f"R2 URL generation failed: {e}")
        return f"/uploads/{file_path}"
