"""Read the newest Gmail messages and turn their bodies into plain text."""

import base64
import html
import re
from typing import Any

from googleapiclient.discovery import build

from attachment_archive import MAX_ARCHIVE_BYTES
from google_client import get_google_credentials


def fetch_recent_gmail_messages(max_results: int = 15, owner_id: str | None = None) -> list[dict[str, Any]]:
    """Return recent inbox messages plus downloadable, non-inline attachments."""
    service = build("gmail", "v1", credentials=get_google_credentials(owner_id), cache_discovery=False)
    response = service.users().messages().list(
        userId="me", labelIds=["INBOX"], maxResults=max_results
    ).execute()

    messages: list[dict[str, str]] = []
    for message_ref in response.get("messages", []):
        message = service.users().messages().get(
            userId="me", id=message_ref["id"], format="full"
        ).execute()
        text = _extract_message_text(message).strip() or message.get("snippet", "").strip()
        attachments = _extract_attachments(service, message)
        if text or attachments:
            attachment_names = ", ".join(attachment["filename"] for attachment in attachments)
            if attachment_names:
                text = f"{text}\nAttachments: {attachment_names}".strip()
            messages.append({"id": message["id"], "text": text or "Attached files", "attachments": attachments})
    return messages


def _extract_message_text(message: dict[str, Any]) -> str:
    """Prefer text/plain MIME content and fall back to stripped text/html."""
    plain_parts: list[str] = []
    html_parts: list[str] = []
    _collect_mime_parts(message.get("payload", {}), plain_parts, html_parts)
    if plain_parts:
        return "\n".join(plain_parts)
    return _strip_html("\n".join(html_parts))


def _collect_mime_parts(
    part: dict[str, Any], plain_parts: list[str], html_parts: list[str]
) -> None:
    mime_type = part.get("mimeType", "")
    body_data = part.get("body", {}).get("data")
    if body_data:
        decoded = _decode_body(body_data)
        if mime_type == "text/plain":
            plain_parts.append(decoded)
        elif mime_type == "text/html":
            html_parts.append(decoded)
    for child_part in part.get("parts", []):
        _collect_mime_parts(child_part, plain_parts, html_parts)


def _extract_attachments(service: Any, message: dict[str, Any]) -> list[dict[str, Any]]:
    """Download named MIME attachments, excluding inline body parts."""
    attachments: list[dict[str, Any]] = []
    for part in _walk_mime_parts(message.get("payload", {})):
        filename = str(part.get("filename") or "").strip()
        attachment_id = part.get("body", {}).get("attachmentId")
        attachment_size = part.get("body", {}).get("size", 0)
        if not filename or not attachment_id or attachment_size > MAX_ARCHIVE_BYTES:
            continue
        response = service.users().messages().attachments().get(
            userId="me", messageId=message["id"], id=attachment_id
        ).execute()
        data = response.get("data")
        if not data:
            continue
        attachments.append(
            {
                "filename": filename,
                "mime_type": part.get("mimeType") or "application/octet-stream",
                "data": _decode_bytes(data),
            }
        )
    return attachments


def _walk_mime_parts(part: dict[str, Any]):
    yield part
    for child_part in part.get("parts", []):
        yield from _walk_mime_parts(child_part)


def _decode_body(body_data: str) -> str:
    return _decode_bytes(body_data).decode("utf-8", errors="replace")


def _decode_bytes(body_data: str) -> bytes:
    padding = "=" * (-len(body_data) % 4)
    return base64.urlsafe_b64decode(body_data + padding)


def _strip_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()
