"""Isolated tests for audit retention and autonomous-work kill-switch controls."""

import gc
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

import database
import sync_jobs


class OperationalControlsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.original_path = database.DATABASE_PATH
        self.original_postgres = database.USING_POSTGRES
        self.original_connection = database._connection
        self.connections: list[sqlite3.Connection] = []
        database.DATABASE_PATH = Path(self.temporary_directory.name) / "operational-controls.db"
        database.USING_POSTGRES = False
        database._connection = self._temporary_connection
        database.initialize_database()
        database.enable_source_connection(
            "gmail", "google-connection:student-a", owner_id="student-a", workspace_id=101,
            selected_channels=["inbox"],
        )

    def _temporary_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(database.DATABASE_PATH)
        connection.row_factory = sqlite3.Row
        self.connections.append(connection)
        return connection

    def tearDown(self) -> None:
        database.DATABASE_PATH = self.original_path
        database.USING_POSTGRES = self.original_postgres
        database._connection = self.original_connection
        for connection in self.connections:
            connection.close()
        gc.collect()
        self.temporary_directory.cleanup()

    def test_kill_switch_cancels_jobs_and_stops_future_scheduling(self) -> None:
        job = sync_jobs.enqueue_sync_job(
            "gmail", workspace_id=101, owner_id="student-a", idempotency_key="test-kill-switch"
        )
        database.set_workspace_kill_switch(101, True, updated_by="student-a")

        self.assertTrue(database.is_workspace_kill_switch_enabled(101))
        self.assertEqual(sync_jobs.get_sync_job(job["id"])["state"], "cancelled")
        self.assertEqual(
            sync_jobs.enqueue_due_sync_jobs(now="2026-07-27T12:00:00+00:00"),
            {"connections_considered": 0, "job_ids": []},
        )

    def test_audit_records_are_minimized_and_retention_only_deletes_operational_data(self) -> None:
        database.record_audit_event(
            workspace_id=101, owner_id="student-a", actor_type="system",
            event_type="source_sync", outcome="failed", error_code="google_sync_failed",
        )
        events = database.get_audit_events(owner_id="student-a", workspace_id=101)
        self.assertEqual(events[0]["error_code"], "google_sync_failed")
        self.assertNotIn("text", events[0])

        with database._connection() as connection:
            connection.execute(
                "UPDATE audit_events SET created_at = ?", ((datetime.now(timezone.utc) - timedelta(days=91)).isoformat(),)
            )
        deleted = database.purge_expired_operational_records(90, now=datetime.now(timezone.utc))

        self.assertEqual(deleted["audit_events"], 1)
        self.assertEqual(database.get_audit_events(owner_id="student-a", workspace_id=101), [])


if __name__ == "__main__":
    unittest.main()
