"""Isolated persistence checks for workspace-scoped source connection records."""

import gc
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

import database


class SourceConnectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.original_path = database.DATABASE_PATH
        self.original_postgres = database.USING_POSTGRES
        self.original_connection = database._connection
        self.connections: list[sqlite3.Connection] = []
        database.DATABASE_PATH = Path(self.temporary_directory.name) / "source-connections.db"
        database.USING_POSTGRES = False
        database._connection = self._temporary_connection
        database.initialize_database()

    def _temporary_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(database.DATABASE_PATH)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
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

    def test_enable_pause_resume_and_health_are_owner_scoped(self) -> None:
        enabled = database.enable_source_connection(
            "gmail",
            "google-connection:student-a",
            owner_id="student-a",
            workspace_id=101,
            selected_channels=["inbox"],
        )
        self.assertEqual(enabled["state"], "enabled")
        self.assertTrue(enabled["has_credential"])
        self.assertNotIn("credential_ref", enabled)
        self.assertEqual(enabled["selected_channels"], ["inbox"])

        paused = database.set_source_connection_state("gmail", "paused", owner_id="student-a")
        self.assertIsNotNone(paused)
        self.assertEqual(paused["state"], "paused")
        self.assertTrue(database.is_source_connection_paused("gmail", owner_id="student-a"))
        self.assertEqual(database.get_source_connections("student-b"), [])

        resumed = database.enable_source_connection(
            "gmail", "google-connection:student-a", owner_id="student-a", workspace_id=101
        )
        self.assertEqual(resumed["state"], "enabled")
        database.record_source_connection_outcome("gmail", succeeded=False, error_message="provider unavailable", owner_id="student-a")
        failed = database.get_source_connection("gmail", owner_id="student-a")
        self.assertEqual(failed["consecutive_failures"], 1)
        self.assertEqual(failed["last_error"], "provider unavailable")

        database.record_source_connection_outcome("gmail", succeeded=True, owner_id="student-a")
        healthy = database.get_source_connection("gmail", owner_id="student-a")
        self.assertEqual(healthy["consecutive_failures"], 0)
        self.assertIsNone(healthy["last_error"])
        self.assertIsNotNone(healthy["last_success_at"])

    def test_invalid_source_and_interval_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported source connection"):
            database.enable_source_connection("slack", "not-yet", owner_id="student-a")
        with self.assertRaisesRegex(ValueError, "Sync interval"):
            database.enable_source_connection("gmail", "google", sync_interval_minutes=10, owner_id="student-a")


if __name__ == "__main__":
    unittest.main()
