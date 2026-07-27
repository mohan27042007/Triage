"""Isolated checks for provider-aware, workspace-scoped item deduplication."""

import gc
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

import database


class SourceDedupeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.original_path = database.DATABASE_PATH
        self.original_postgres = database.USING_POSTGRES
        self.original_connection = database._connection
        self.connections: list[sqlite3.Connection] = []
        database.DATABASE_PATH = Path(self.temporary_directory.name) / "source-dedupe.db"
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

    @staticmethod
    def _classification() -> dict[str, object]:
        return {
            "category": "Obligation",
            "reason": "Test fixture",
            "deadline": None,
            "mandatory": True,
            "is_poll_or_form": False,
        }

    def test_workspace_dedupe_includes_provider_and_workspace(self) -> None:
        gmail_item = database.create_item(
            "Gmail task",
            self._classification(),
            source="gmail",
            source_id="shared-provider-id",
            owner_id="student-a",
            workspace_id=101,
        )
        classroom_item = database.create_item(
            "Classroom task",
            self._classification(),
            source="classroom",
            source_id="shared-provider-id",
            owner_id="student-a",
            workspace_id=101,
        )
        duplicate_gmail = database.create_item(
            "Duplicate Gmail task",
            self._classification(),
            source="gmail",
            source_id="shared-provider-id",
            owner_id="student-a",
            workspace_id=101,
        )
        other_workspace_item = database.create_item(
            "Other workspace Gmail task",
            self._classification(),
            source="gmail",
            source_id="shared-provider-id",
            owner_id="student-b",
            workspace_id=202,
        )

        self.assertIsNotNone(gmail_item)
        self.assertIsNotNone(classroom_item)
        self.assertEqual(duplicate_gmail["id"], gmail_item["id"])
        self.assertNotEqual(classroom_item["id"], gmail_item["id"])
        self.assertNotEqual(other_workspace_item["id"], gmail_item["id"])
        self.assertEqual(
            database.get_item_by_source_id("gmail", "shared-provider-id", workspace_id=101)["id"],
            gmail_item["id"],
        )

    def test_local_fallback_keeps_provider_in_the_identity_key(self) -> None:
        gmail_item = database.create_item(
            "Local Gmail task",
            self._classification(),
            source="gmail",
            source_id="local-id",
            owner_id="local-a",
        )
        classroom_item = database.create_item(
            "Local Classroom task",
            self._classification(),
            source="classroom",
            source_id="local-id",
            owner_id="local-a",
        )
        duplicate_gmail = database.create_item(
            "Duplicate local Gmail task",
            self._classification(),
            source="gmail",
            source_id="local-id",
            owner_id="local-a",
        )

        self.assertNotEqual(gmail_item["id"], classroom_item["id"])
        self.assertEqual(duplicate_gmail["id"], gmail_item["id"])


if __name__ == "__main__":
    unittest.main()
