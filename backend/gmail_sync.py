"""Read the newest Gmail messages and turn their bodies into plain text."""

import base64
import html
import re
from typing import Any

from googleapiclient.discovery import build

from google_client import get_google_credentials


def fetch_recent_gmail_messages(max_results: int = 15) -> list[dict[str, str]]:
    """Return recent inbox message IDs with a usable plain-text body."""
    service = build("gmail", "v1", credentials=get_google_credentials(), cache_discovery=False)
    response = service.users().messages().list(
        userId="me", labelIds=["INBOX"], maxResults=max_results
    ).execute()

    messages: list[dict[str, str]] = []
    for message_ref in response.get("messages", []):
        message = service.users().messages().get(
            userId="me", id=message_ref["id"], format="full"
        ).execute()
        text = _extract_message_text(message).strip() or message.get("snippet", "").strip()
        if text:
            messages.append({"id": message["id"], "text": text})
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


def _decode_body(body_data: str) -> str:
    padding = "=" * (-len(body_data) % 4)
    return base64.urlsafe_b64decode(body_data + padding).decode("utf-8", errors="replace")


def _strip_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()
