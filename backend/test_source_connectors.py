"""Isolated adapter checks for normalized, provider-specific source connectors."""

import unittest

import source_connectors


class SourceConnectorTests(unittest.TestCase):
    def test_gmail_adapter_preserves_normalized_items_and_cursor(self) -> None:
        original_fetch = source_connectors.fetch_recent_gmail_messages
        source_connectors.fetch_recent_gmail_messages = lambda **kwargs: [
            {"id": "message-1", "text": "Deadline Friday", "attachments": [{"filename": "brief.pdf"}]}
        ]
        try:
            result = source_connectors.get_source_connector("gmail").fetch_changes(
                source_connectors.SourceConnection("gmail", "student-a", 101), "opaque-cursor"
            )
        finally:
            source_connectors.fetch_recent_gmail_messages = original_fetch

        self.assertEqual(result.next_cursor, "opaque-cursor")
        self.assertEqual(result.items[0].source_id, "message-1")
        self.assertEqual(result.items[0].text, "Deadline Friday")
        self.assertEqual(result.items[0].attachments, [{"filename": "brief.pdf"}])

    def test_classroom_adapter_preserves_normalized_items_and_cursor(self) -> None:
        original_fetch = source_connectors.fetch_recent_classroom_items
        source_connectors.fetch_recent_classroom_items = lambda **kwargs: [
            {"id": "classroom:coursework:1:2", "text": "Read chapter", "attachments": []}
        ]
        try:
            result = source_connectors.get_source_connector("classroom").fetch_changes(
                source_connectors.SourceConnection("classroom", "student-a", 101), None
            )
        finally:
            source_connectors.fetch_recent_classroom_items = original_fetch

        self.assertIsNone(result.next_cursor)
        self.assertEqual(result.items[0].source_id, "classroom:coursework:1:2")

    def test_invalid_connector_and_provider_item_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported source connector"):
            source_connectors.get_source_connector("slack")

        original_fetch = source_connectors.fetch_recent_gmail_messages
        source_connectors.fetch_recent_gmail_messages = lambda **kwargs: [{"id": "message-1", "text": "", "attachments": []}]
        try:
            with self.assertRaisesRegex(RuntimeError, "invalid normalized item"):
                source_connectors.get_source_connector("gmail").fetch_changes(
                    source_connectors.SourceConnection("gmail", "student-a", 101), None
                )
        finally:
            source_connectors.fetch_recent_gmail_messages = original_fetch


if __name__ == "__main__":
    unittest.main()
