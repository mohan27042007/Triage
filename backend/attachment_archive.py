"""Private attachment retention with a local fallback and S3-compatible hosting."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any
from uuid import uuid4


MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
S3_BACKEND = "s3"


def using_durable_storage() -> bool:
    """Return whether the configured archive backend is S3-compatible storage."""
    return os.getenv("ARCHIVE_STORAGE_BACKEND", "local").strip().lower() == S3_BACKEND


def archive_attachment(
    archive_directory: Path,
    original_filename: str,
    file_bytes: bytes,
    mime_type: str | None = None,
    owner_id: str = "local-demo",
) -> dict[str, Any] | None:
    """Retain one bounded attachment privately and return safe download metadata.

    Local development keeps using ``backend/archive``. Hosted deployments can
    opt into an S3-compatible bucket (including Cloudflare R2); object names
    are private and are never exposed as public bucket URLs.
    """
    if not isinstance(file_bytes, bytes) or not file_bytes or len(file_bytes) > MAX_ARCHIVE_BYTES:
        return None

    filename = _safe_filename(original_filename)
    archived_path = f"{uuid4().hex}_{filename}"
    content_type = mime_type or "application/octet-stream"
    if using_durable_storage():
        try:
            _s3_client().put_object(
                Bucket=_required_s3_setting("S3_BUCKET"),
                Key=_object_key(owner_id, archived_path),
                Body=file_bytes,
                ContentType=content_type,
            )
        except RuntimeError:
            raise
        except Exception as exc:  # SDK errors are normalized without leaking credentials.
            raise RuntimeError("Could not retain the attachment in durable storage.") from exc
    else:
        archive_directory.mkdir(parents=True, exist_ok=True)
        (archive_directory / archived_path).write_bytes(file_bytes)
    return {
        "archived_path": archived_path,
        "filename": filename,
        "mime_type": content_type,
        "size": len(file_bytes),
    }


def archive_source_attachments(
    archive_directory: Path,
    attachments: list[dict[str, Any]] | None,
    owner_id: str = "local-demo",
) -> list[dict[str, Any]]:
    """Archive valid source attachment payloads, omitting unavailable files."""
    archived: list[dict[str, Any]] = []
    for attachment in attachments or []:
        result = archive_attachment(
            archive_directory,
            str(attachment.get("filename") or "attachment"),
            attachment.get("data", b""),
            attachment.get("mime_type"),
            owner_id,
        )
        if result:
            archived.append(result)
    return archived


def archived_file_exists(archive_directory: Path, archived_path: str, owner_id: str = "local-demo") -> bool:
    """Check storage availability without exposing an object outside its owner."""
    if not _is_safe_archive_id(archived_path):
        return False
    if not using_durable_storage():
        return (archive_directory / archived_path).is_file()
    try:
        _s3_client().head_object(Bucket=_required_s3_setting("S3_BUCKET"), Key=_object_key(owner_id, archived_path))
        return True
    except Exception as exc:
        if _is_missing_object_error(exc):
            return False
        raise RuntimeError("Could not check durable attachment storage.") from exc


def read_archived_file(archive_directory: Path, archived_path: str, owner_id: str = "local-demo") -> bytes | None:
    """Read one owner-scoped archived file for Triage's authenticated download route."""
    if not _is_safe_archive_id(archived_path):
        return None
    if not using_durable_storage():
        path = archive_directory / archived_path
        return path.read_bytes() if path.is_file() else None
    try:
        response = _s3_client().get_object(
            Bucket=_required_s3_setting("S3_BUCKET"), Key=_object_key(owner_id, archived_path)
        )
        return response["Body"].read()
    except Exception as exc:
        if _is_missing_object_error(exc):
            return None
        raise RuntimeError("Could not retrieve the archived attachment from durable storage.") from exc


def original_filename_from_archive(archived_path: str) -> str:
    """Recover the user-facing filename from Triage's UUID-prefixed archive name."""
    return re.sub(r"^[0-9a-f]{32}_", "", archived_path, count=1) or "attachment"


def _object_key(owner_id: str, archived_path: str) -> str:
    """Use a non-reversible owner namespace so object listing reveals no account IDs."""
    prefix = os.getenv("S3_PREFIX", "triage").strip("/ ") or "triage"
    owner_namespace = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()
    return f"{prefix}/{owner_namespace}/{archived_path}"


def _s3_client():
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("Durable attachment storage requires boto3.") from exc
    return boto3.client(
        "s3",
        endpoint_url=_required_s3_setting("S3_ENDPOINT_URL"),
        region_name=os.getenv("S3_REGION", "auto").strip() or "auto",
        aws_access_key_id=_required_s3_setting("S3_ACCESS_KEY_ID"),
        aws_secret_access_key=_required_s3_setting("S3_SECRET_ACCESS_KEY"),
    )


def _required_s3_setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"ARCHIVE_STORAGE_BACKEND=s3 requires {name}.")
    return value


def _is_safe_archive_id(value: str) -> bool:
    return bool(value) and "/" not in value and "\\" not in value and ".." not in value


def _is_missing_object_error(error: Exception) -> bool:
    """Recognize the portable S3/R2 not-found shapes without leaking SDK details."""
    if isinstance(error, FileNotFoundError):
        return True
    response = getattr(error, "response", {})
    code = str(response.get("Error", {}).get("Code", "")) if isinstance(response, dict) else ""
    return code in {"404", "NoSuchKey", "NotFound", "NoSuchObject"}


def _safe_filename(value: str) -> str:
    name = Path(value).name.strip()
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", name).strip(". ")
    return (name[:120] or "attachment")
