"""Narrow provider adapters for normalized, read-only source collection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

@dataclass(frozen=True)
class SourceConnection:
    """The non-secret connection state a connector needs for one collection run."""

    source: str
    owner_id: str
    workspace_id: int | None
    selected_channels: tuple[str, ...] = ()
    provider_cursor: str | None = None


@dataclass(frozen=True)
class NormalizedSourceItem:
    source_id: str
    text: str
    attachments: list[dict[str, Any]]


@dataclass(frozen=True)
class FetchResult:
    """Normalized changes and an opaque next cursor that the caller may persist later."""

    items: list[NormalizedSourceItem]
    next_cursor: str | None


@dataclass(frozen=True)
class ConnectionHealth:
    healthy: bool
    error_code: str | None = None


class SourceConnector(Protocol):
    source_name: str

    def fetch_changes(self, connection: SourceConnection, cursor: str | None) -> FetchResult:
        """Return normalized source items and an uncommitted opaque cursor."""

    def validate_connection(self, connection: SourceConnection) -> ConnectionHealth:
        """Perform a small provider permission/token check without writing data."""


class GmailConnector:
    source_name = "gmail"

    def fetch_changes(self, connection: SourceConnection, cursor: str | None) -> FetchResult:
        _require_source(connection, self.source_name)
        messages = fetch_recent_gmail_messages(owner_id=connection.owner_id)
        return FetchResult(items=_normalize_items(messages), next_cursor=cursor)

    def validate_connection(self, connection: SourceConnection) -> ConnectionHealth:
        _require_source(connection, self.source_name)
        try:
            from googleapiclient.discovery import build

            service = build("gmail", "v1", credentials=get_google_credentials(connection.owner_id), cache_discovery=False)
            service.users().getProfile(userId="me").execute()
        except Exception:
            return ConnectionHealth(healthy=False, error_code="gmail_connection_unavailable")
        return ConnectionHealth(healthy=True)


class ClassroomConnector:
    source_name = "classroom"

    def fetch_changes(self, connection: SourceConnection, cursor: str | None) -> FetchResult:
        _require_source(connection, self.source_name)
        items = fetch_recent_classroom_items(owner_id=connection.owner_id)
        return FetchResult(items=_normalize_items(items), next_cursor=cursor)

    def validate_connection(self, connection: SourceConnection) -> ConnectionHealth:
        _require_source(connection, self.source_name)
        try:
            from googleapiclient.discovery import build

            service = build("classroom", "v1", credentials=get_google_credentials(connection.owner_id), cache_discovery=False)
            service.courses().list(courseStates=["ACTIVE"], pageSize=1).execute()
        except Exception:
            return ConnectionHealth(healthy=False, error_code="classroom_connection_unavailable")
        return ConnectionHealth(healthy=True)


_CONNECTORS: dict[str, SourceConnector] = {
    "gmail": GmailConnector(),
    "classroom": ClassroomConnector(),
}


def get_source_connector(source: str) -> SourceConnector:
    """Return one registered read-only connector without introducing fallback behavior."""
    try:
        return _CONNECTORS[source]
    except KeyError as exc:
        raise ValueError("Unsupported source connector.") from exc


def fetch_recent_gmail_messages(*, owner_id: str) -> list[dict[str, Any]]:
    """Load the optional Gmail integration only when a Gmail connector runs."""
    from gmail_sync import fetch_recent_gmail_messages as fetch

    return fetch(owner_id=owner_id)


def fetch_recent_classroom_items(*, owner_id: str) -> list[dict[str, Any]]:
    """Load the optional Classroom integration only when its connector runs."""
    from classroom_sync import fetch_recent_classroom_items as fetch

    return fetch(owner_id=owner_id)


def get_google_credentials(owner_id: str):
    """Load optional Google credential support only for explicit health checks."""
    from google_client import get_google_credentials as get_credentials

    return get_credentials(owner_id)


def _normalize_items(items: list[dict[str, Any]]) -> list[NormalizedSourceItem]:
    normalized: list[NormalizedSourceItem] = []
    for item in items:
        source_id = item.get("id")
        text = item.get("text")
        if not isinstance(source_id, str) or not source_id or not isinstance(text, str) or not text.strip():
            raise RuntimeError("Source connector returned an invalid normalized item.")
        attachments = item.get("attachments") or []
        if not isinstance(attachments, list):
            raise RuntimeError("Source connector returned invalid attachments.")
        normalized.append(NormalizedSourceItem(source_id=source_id, text=text, attachments=attachments))
    return normalized


def _require_source(connection: SourceConnection, source: str) -> None:
    if connection.source != source:
        raise ValueError(f"Expected {source} connection.")
