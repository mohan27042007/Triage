"""Shared, inert persistence path for manually or worker-collected source items."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from attachment_archive import archive_source_attachments
from classifier import classify
from database import create_item, get_item_by_source_id
from source_connectors import SourceConnection, get_source_connector


def ingest_source_changes(
    source: str,
    *,
    owner_id: str,
    workspace_id: int | None,
    selected_channels: tuple[str, ...] = (),
    provider_cursor: str | None = None,
    archive_directory: Path,
) -> dict[str, Any]:
    """Read, classify, archive, and persist source items without any external action."""
    result = get_source_connector(source).fetch_changes(
        SourceConnection(
            source=source,
            owner_id=owner_id,
            workspace_id=workspace_id,
            selected_channels=selected_channels,
            provider_cursor=provider_cursor,
        ),
        provider_cursor,
    )
    processed = 0
    skipped = 0
    for item in result.items:
        if get_item_by_source_id(source, item.source_id, owner_id=owner_id, workspace_id=workspace_id):
            skipped += 1
            continue
        classification = classify(item.text)
        _validate_classification(classification)
        create_item(
            item.text,
            classification,
            attachments=archive_source_attachments(archive_directory, item.attachments, owner_id),
            source=source,
            source_id=item.source_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )
        processed += 1
    return {"processed": processed, "skipped": skipped, "next_cursor": result.next_cursor}


def _validate_classification(classification: object) -> None:
    if not isinstance(classification, dict):
        raise RuntimeError("Classifier returned an invalid result.")
    if classification.get("category") not in {"Obligation", "Study Material", "Noise"}:
        raise RuntimeError("Classifier returned an invalid category.")
    if not isinstance(classification.get("reason"), str) or not classification["reason"].strip():
        raise RuntimeError("Classifier returned an invalid reason.")
    if classification.get("deadline") is not None and not isinstance(classification["deadline"], str):
        raise RuntimeError("Classifier returned an invalid deadline.")
    if classification.get("mandatory") not in {True, False, None}:
        raise RuntimeError("Classifier returned an invalid mandatory value.")
