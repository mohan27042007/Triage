"""Safe, local-only storage for files retained by Triage source syncs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import uuid4


MAX_ARCHIVE_BYTES = 20 * 1024 * 1024


def archive_attachment(
    archive_directory: Path,
    original_filename: str,
    file_bytes: bytes,
    mime_type: str | None = None,
) -> dict[str, Any] | None:
    """Copy one bounded attachment locally and return safe download metadata.

    Attachments are deliberately retained only on the machine running Triage.
    Files above the local safety limit are skipped rather than partially copied.
    """
    if not isinstance(file_bytes, bytes) or not file_bytes or len(file_bytes) > MAX_ARCHIVE_BYTES:
        return None

    filename = _safe_filename(original_filename)
    archive_directory.mkdir(parents=True, exist_ok=True)
    archived_path = f"{uuid4().hex}_{filename}"
    (archive_directory / archived_path).write_bytes(file_bytes)
    return {
        "archived_path": archived_path,
        "filename": filename,
        "mime_type": mime_type or "application/octet-stream",
        "size": len(file_bytes),
    }


def archive_source_attachments(
    archive_directory: Path, attachments: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Archive valid source attachment payloads, omitting unavailable files."""
    archived: list[dict[str, Any]] = []
    for attachment in attachments or []:
        result = archive_attachment(
            archive_directory,
            str(attachment.get("filename") or "attachment"),
            attachment.get("data", b""),
            attachment.get("mime_type"),
        )
        if result:
            archived.append(result)
    return archived


def original_filename_from_archive(archived_path: str) -> str:
    """Recover the user-facing filename from Triage's UUID-prefixed archive name."""
    return re.sub(r"^[0-9a-f]{32}_", "", archived_path, count=1) or "attachment"


def _safe_filename(value: str) -> str:
    name = Path(value).name.strip()
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", name).strip(". ")
    return (name[:120] or "attachment")
