"""Opt-in executor for the narrowly scoped autonomous Google pilot."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from database import (
    get_source_connection_runtime,
    record_source_connection_outcome,
    record_source_sync,
)
from evaluation import quality_gate_failures
from source_ingestion import ingest_source_changes


ARCHIVE_DIRECTORY = Path(__file__).with_name("archive")


class PilotBlockedError(RuntimeError):
    """A configuration/policy condition that must be visible in the job outcome."""

    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


def execute_sync_job(job: dict[str, Any]) -> dict[str, Any]:
    """Execute one allowed Google job; it only reads/classifies/persists inert records."""
    _require_pilot_gate(job)
    source = job["source"]
    owner_id = job["owner_id"]
    workspace_id = int(job["workspace_id"])
    connection = get_source_connection_runtime(source, owner_id=owner_id)
    if connection is None or connection["workspace_id"] != workspace_id:
        raise PilotBlockedError("source_connection_missing")
    if connection["state"] != "enabled":
        raise PilotBlockedError("source_connection_not_enabled")
    channels = tuple(connection["selected_channels"])
    if not channels:
        raise PilotBlockedError("source_selection_required")
    try:
        outcome = ingest_source_changes(
            source,
            owner_id=owner_id,
            workspace_id=workspace_id,
            selected_channels=channels,
            provider_cursor=connection["provider_cursor"],
            archive_directory=ARCHIVE_DIRECTORY,
        )
    except RuntimeError as exc:
        error_code = "google_sync_failed"
        record_source_sync(source, succeeded=False, error_message=error_code, owner_id=owner_id, workspace_id=workspace_id)
        record_source_connection_outcome(source, succeeded=False, error_message=error_code, owner_id=owner_id)
        raise PilotBlockedError(error_code) from exc
    record_source_sync(source, succeeded=True, imported_count=outcome["processed"], owner_id=owner_id, workspace_id=workspace_id)
    record_source_connection_outcome(source, succeeded=True, owner_id=owner_id)
    return {"processed": outcome["processed"], "skipped": outcome["skipped"], "source": source}


def _require_pilot_gate(job: dict[str, Any]) -> None:
    if os.getenv("AUTONOMOUS_GOOGLE_SYNC_ENABLED", "").lower() != "true":
        raise PilotBlockedError("autonomous_google_sync_disabled")
    allowed_workspaces = {
        int(value)
        for value in os.getenv("AUTONOMOUS_GOOGLE_PILOT_WORKSPACE_IDS", "").split(",")
        if value.strip().isdigit()
    }
    if not allowed_workspaces or int(job["workspace_id"]) not in allowed_workspaces:
        raise PilotBlockedError("workspace_not_in_google_pilot")
    try:
        metrics = json.loads(os.environ["AUTONOMOUS_EVALUATION_METRICS_JSON"])
        failures = quality_gate_failures(metrics)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise PilotBlockedError("evaluation_metrics_missing_or_invalid") from None
    if failures:
        raise PilotBlockedError("evaluation_gate_failed")
