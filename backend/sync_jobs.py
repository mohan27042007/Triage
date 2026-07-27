"""Durable, leased sync-job queue primitives for future source workers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import json
import secrets
from typing import Any

import database


JOB_STATES = {"queued", "running", "succeeded", "failed", "cancelled"}
DEFAULT_LEASE_SECONDS = 300
DEFAULT_MAX_ATTEMPTS = 5


def enqueue_sync_job(
    source: str,
    *,
    workspace_id: int,
    owner_id: str,
    idempotency_key: str,
    available_at: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict[str, Any]:
    """Queue one workspace source run, returning an existing idempotent job if present."""
    _validate_job_inputs(source, workspace_id, owner_id, idempotency_key, max_attempts)
    available = available_at or _utcnow()
    with database._connection() as connection:
        connection.execute(
            """
            INSERT INTO sync_jobs (
                workspace_id, owner_id, source, idempotency_key, state, available_at, max_attempts, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)
            ON CONFLICT (workspace_id, source, idempotency_key) DO NOTHING
            """,
            (workspace_id, owner_id, source, idempotency_key, available, max_attempts, _utcnow(), _utcnow()),
        )
        row = connection.execute(
            """
            SELECT * FROM sync_jobs
            WHERE workspace_id = ? AND source = ? AND idempotency_key = ?
            """,
            (workspace_id, source, idempotency_key),
        ).fetchone()
    if row is None:
        raise RuntimeError("Could not enqueue sync job.")
    return _row_to_job(row)


def enqueue_due_sync_jobs(*, now: str | None = None) -> dict[str, Any]:
    """Enqueue one idempotent time-window job for each due enabled connection."""
    scheduled_at = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
    if scheduled_at.tzinfo is None:
        raise ValueError("Schedule time must include a timezone offset.")
    scheduled_at = scheduled_at.astimezone(timezone.utc)
    with database._connection() as connection:
        connections = connection.execute(
            """
            SELECT source_connections.owner_id, source_connections.workspace_id,
                   source_connections.source, source_connections.selected_channels,
                   source_connections.sync_interval_minutes
            FROM source_connections
            LEFT JOIN workspace_kill_switches
              ON workspace_kill_switches.workspace_id = source_connections.workspace_id
            WHERE source_connections.state = 'enabled'
              AND source_connections.workspace_id IS NOT NULL
              AND COALESCE(workspace_kill_switches.enabled, FALSE) = FALSE
            ORDER BY source_connections.workspace_id ASC, source_connections.source ASC
            """
        ).fetchall()
    job_ids: list[int] = []
    for connection in connections:
        selected_channels = json.loads(connection["selected_channels"])
        if not isinstance(selected_channels, list) or not selected_channels:
            continue
        interval_minutes = int(connection["sync_interval_minutes"])
        window_start = _schedule_window_start(scheduled_at, interval_minutes)
        job = enqueue_sync_job(
            connection["source"],
            workspace_id=int(connection["workspace_id"]),
            owner_id=connection["owner_id"],
            idempotency_key=(
                f"scheduled:{connection['workspace_id']}:{connection['source']}:{int(window_start.timestamp())}"
            ),
            available_at=scheduled_at.isoformat(),
        )
        job_ids.append(int(job["id"]))
    return {"connections_considered": len(job_ids), "job_ids": job_ids}


def claim_next_sync_job(
    worker_id: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: str | None = None,
) -> dict[str, Any] | None:
    """Atomically lease one due job, allowing expired leases to be recovered."""
    if not worker_id.strip():
        raise ValueError("Worker ID is required.")
    if not 30 <= lease_seconds <= 3_600:
        raise ValueError("Lease duration must be between 30 and 3600 seconds.")
    claimed_at = now or _utcnow()
    lease_expires_at = _after_seconds(claimed_at, lease_seconds)
    lease_token = secrets.token_urlsafe(24)
    with database._connection() as connection:
        if database.USING_POSTGRES:
            row = connection.execute(
                """
                WITH claimable AS (
                    SELECT sync_jobs.id
                    FROM sync_jobs
                    JOIN source_connections
                      ON source_connections.owner_id = sync_jobs.owner_id
                     AND source_connections.source = sync_jobs.source
                    LEFT JOIN workspace_kill_switches
                      ON workspace_kill_switches.workspace_id = sync_jobs.workspace_id
                    WHERE (
                        (sync_jobs.state = 'queued' AND sync_jobs.available_at <= NOW())
                        OR (sync_jobs.state = 'running' AND sync_jobs.lease_expires_at <= NOW())
                    )
                      AND sync_jobs.attempt_count < sync_jobs.max_attempts
                      AND source_connections.state = 'enabled'
                      AND COALESCE(workspace_kill_switches.enabled, FALSE) = FALSE
                    ORDER BY sync_jobs.available_at ASC, sync_jobs.id ASC
                    FOR UPDATE OF sync_jobs SKIP LOCKED
                    LIMIT 1
                )
                UPDATE sync_jobs
                SET state = 'running',
                    attempt_count = sync_jobs.attempt_count + 1,
                    lease_token = ?,
                    lease_expires_at = NOW() + (? * INTERVAL '1 second'),
                    started_at = COALESCE(sync_jobs.started_at, NOW()),
                    updated_at = NOW()
                FROM claimable
                WHERE sync_jobs.id = claimable.id
                RETURNING sync_jobs.*
                """,
                (lease_token, lease_seconds),
            ).fetchone()
        else:
            connection.execute("BEGIN IMMEDIATE")
            candidate = connection.execute(
                """
                SELECT sync_jobs.id
                FROM sync_jobs
                JOIN source_connections
                  ON source_connections.owner_id = sync_jobs.owner_id
                 AND source_connections.source = sync_jobs.source
                LEFT JOIN workspace_kill_switches
                  ON workspace_kill_switches.workspace_id = sync_jobs.workspace_id
                WHERE (
                    (sync_jobs.state = 'queued' AND sync_jobs.available_at <= ?)
                    OR (sync_jobs.state = 'running' AND sync_jobs.lease_expires_at <= ?)
                )
                  AND sync_jobs.attempt_count < sync_jobs.max_attempts
                  AND source_connections.state = 'enabled'
                  AND COALESCE(workspace_kill_switches.enabled, FALSE) = FALSE
                ORDER BY sync_jobs.available_at ASC, sync_jobs.id ASC
                LIMIT 1
                """,
                (claimed_at, claimed_at),
            ).fetchone()
            if candidate is None:
                return None
            connection.execute(
                """
                UPDATE sync_jobs
                SET state = 'running', attempt_count = attempt_count + 1, lease_token = ?,
                    lease_expires_at = ?, started_at = COALESCE(started_at, ?), updated_at = ?
                WHERE id = ?
                """,
                (lease_token, lease_expires_at, claimed_at, claimed_at, candidate["id"]),
            )
            row = connection.execute("SELECT * FROM sync_jobs WHERE id = ?", (candidate["id"],)).fetchone()
    return _row_to_job(row) if row else None


def complete_sync_job(job_id: int, lease_token: str, outcome: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Mark a currently leased job successful only when its lease token matches."""
    return _finish_sync_job(job_id, lease_token, state="succeeded", outcome=outcome)


def fail_sync_job(
    job_id: int,
    lease_token: str,
    error_code: str,
    *,
    retry_after_seconds: int | None = None,
) -> dict[str, Any] | None:
    """Release a failed job for bounded retry, or terminally fail it after its limit."""
    if not error_code.strip() or len(error_code) > 80:
        raise ValueError("Error code must be between 1 and 80 characters.")
    now = _utcnow()
    with database._connection() as connection:
        job = connection.execute(
            "SELECT * FROM sync_jobs WHERE id = ? AND state = 'running' AND lease_token = ?",
            (job_id, lease_token),
        ).fetchone()
        if job is None:
            return None
        attempts = int(job["attempt_count"])
        terminal = attempts >= int(job["max_attempts"])
        delay = retry_after_seconds if retry_after_seconds is not None else _retry_delay_seconds(attempts)
        if delay < 0 or delay > 3_600:
            raise ValueError("Retry delay must be between 0 and 3600 seconds.")
        state = "failed" if terminal else "queued"
        available_at = now if terminal else _after_seconds(now, delay)
        connection.execute(
            """
            UPDATE sync_jobs
            SET state = ?, available_at = ?, lease_token = NULL, lease_expires_at = NULL,
                completed_at = CASE WHEN ? = 'failed' THEN ? ELSE completed_at END,
                last_error_code = ?, updated_at = ?
            WHERE id = ? AND state = 'running' AND lease_token = ?
            """,
            (state, available_at, state, now, error_code.strip(), now, job_id, lease_token),
        )
        row = connection.execute("SELECT * FROM sync_jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def cancel_sync_jobs_for_source(source: str, *, owner_id: str) -> int:
    """Cancel queued or leased work when a connection is paused."""
    with database._connection() as connection:
        cursor = connection.execute(
            """
            UPDATE sync_jobs
            SET state = 'cancelled', lease_token = NULL, lease_expires_at = NULL,
                completed_at = ?, updated_at = ?
            WHERE source = ? AND owner_id = ? AND state IN ('queued', 'running')
            """,
            (_utcnow(), _utcnow(), source, owner_id),
        )
    return cursor.rowcount


def get_sync_job(job_id: int) -> dict[str, Any] | None:
    with database._connection() as connection:
        row = connection.execute("SELECT * FROM sync_jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def run_once(executor: Callable[[dict[str, Any]], dict[str, Any] | None], *, worker_id: str) -> dict[str, Any]:
    """Claim and execute one job; the supplied executor keeps source behavior separate."""
    job = claim_next_sync_job(worker_id)
    if job is None:
        return {"status": "idle"}
    try:
        outcome = executor(job) or {}
    except Exception as exc:
        error_code = getattr(exc, "error_code", "worker_execution_failed")
        failed = fail_sync_job(job["id"], job["lease_token"], error_code)
        return {"status": "failed", "job": failed}
    completed = complete_sync_job(job["id"], job["lease_token"], outcome)
    return {"status": "succeeded", "job": completed}


def _finish_sync_job(
    job_id: int, lease_token: str, *, state: str, outcome: dict[str, Any] | None
) -> dict[str, Any] | None:
    if state not in JOB_STATES:
        raise ValueError("Unsupported job state.")
    safe_outcome = json.dumps(outcome or {}, separators=(",", ":"))
    if len(safe_outcome) > 1_000:
        raise ValueError("Job outcome must be at most 1000 serialized characters.")
    now = _utcnow()
    with database._connection() as connection:
        if database.USING_POSTGRES:
            cursor = connection.execute(
                """
                UPDATE sync_jobs
                SET state = ?, outcome = ?::jsonb, lease_token = NULL, lease_expires_at = NULL,
                    completed_at = ?, updated_at = ?
                WHERE id = ? AND state = 'running' AND lease_token = ?
                """,
                (state, safe_outcome, now, now, job_id, lease_token),
            )
        else:
            cursor = connection.execute(
                """
                UPDATE sync_jobs
                SET state = ?, outcome = ?, lease_token = NULL, lease_expires_at = NULL,
                    completed_at = ?, updated_at = ?
                WHERE id = ? AND state = 'running' AND lease_token = ?
                """,
                (state, safe_outcome, now, now, job_id, lease_token),
            )
        if cursor.rowcount != 1:
            return None
        row = connection.execute("SELECT * FROM sync_jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def _validate_job_inputs(source: str, workspace_id: int, owner_id: str, idempotency_key: str, max_attempts: int) -> None:
    if source not in database.VALID_CONNECTED_SOURCES:
        raise ValueError("Unsupported sync job source.")
    if not isinstance(workspace_id, int) or workspace_id < 1:
        raise ValueError("Sync jobs require a hosted workspace ID.")
    if not owner_id.strip():
        raise ValueError("Sync jobs require an owner ID.")
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise ValueError("Idempotency key must be between 1 and 200 characters.")
    if not 1 <= max_attempts <= DEFAULT_MAX_ATTEMPTS:
        raise ValueError("Max attempts must be between 1 and 5.")


def _row_to_job(row: Any) -> dict[str, Any]:
    job = dict(row)
    outcome = job["outcome"]
    job["outcome"] = json.loads(outcome) if isinstance(outcome, str) and outcome else outcome
    return job


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _after_seconds(value: str, seconds: int) -> str:
    return (datetime.fromisoformat(value) + timedelta(seconds=seconds)).isoformat()


def _retry_delay_seconds(attempt_count: int) -> int:
    delay = min(3_600, 60 * (2 ** max(attempt_count - 1, 0)))
    return delay + secrets.randbelow(max(1, delay // 4))


def _schedule_window_start(scheduled_at: datetime, interval_minutes: int) -> datetime:
    interval_seconds = interval_minutes * 60
    window_epoch = int(scheduled_at.timestamp()) // interval_seconds * interval_seconds
    return datetime.fromtimestamp(window_epoch, timezone.utc)
