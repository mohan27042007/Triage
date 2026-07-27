"""Isolated checks for deterministic policy routing and item persistence."""

import gc
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

import database
from policy_routing import route_policy


class PolicyRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.original_path = database.DATABASE_PATH
        self.original_postgres = database.USING_POSTGRES
        self.original_connection = database._connection
        self.connections: list[sqlite3.Connection] = []
        database.DATABASE_PATH = Path(self.temporary_directory.name) / "policy-routing.db"
        database.USING_POSTGRES = False
        database._connection = self._temporary_connection
        database.initialize_database()

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

    def test_deterministic_rules_do_not_use_model_confidence(self) -> None:
        policy = route_policy(
            "Attendance is mandatory but optional for some students. Reply YES.",
            {"category": "Obligation", "deadline": None, "is_poll_or_form": True, "confidence": 0.99},
        )

        self.assertTrue(policy["review_required"])
        self.assertTrue(policy["draft_eligible"])
        self.assertEqual(
            policy["review_reasons"],
            [
                "obligation_missing_deadline",
                "conflicting_requirement_language",
                "external_action_requires_human_review",
            ],
        )

    def test_policy_fields_are_persisted_with_items(self) -> None:
        item = database.create_item(
            "Submit the registration form.",
            {
                "category": "Obligation",
                "reason": "Registration request",
                "deadline": None,
                "mandatory": True,
                "is_poll_or_form": True,
            },
        )

        self.assertTrue(item["review_required"])
        self.assertTrue(item["draft_eligible"])
        self.assertEqual(
            item["review_reasons"],
            ["obligation_missing_deadline", "external_action_requires_human_review"],
        )


if __name__ == "__main__":
    unittest.main()
