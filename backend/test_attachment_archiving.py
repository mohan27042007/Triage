"""Small isolated checks for the local attachment-retention path.

Run with: python test_attachment_archiving.py
This test never opens backend/triage.db or backend/archive/.
"""

import gc
from pathlib import Path
from tempfile import TemporaryDirectory

from attachment_archive import archive_attachment, archive_source_attachments
from classroom_sync import _download_materials
import database
from gmail_sync import _extract_attachments


class _Result:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class _GmailAttachments:
    def get(self, **_kwargs):
        return _Result({"data": "c2F2ZWQ="})


class _GmailService:
    def users(self):
        return self

    def messages(self):
        return self

    def attachments(self):
        return _GmailAttachments()


class _DriveFiles:
    def get(self, **_kwargs):
        return _Result({"name": "schedule.pdf", "mimeType": "application/pdf", "size": "5"})

    def get_media(self, **_kwargs):
        return _Result(b"drive")


class _DriveService:
    def files(self):
        return _DriveFiles()


def main() -> None:
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        archive_root = root / "archive"

        archived = archive_attachment(
            archive_root, "../DRMS:record?.pdf", b"example attachment", "application/pdf"
        )
        assert archived is not None
        assert archived["filename"] == "DRMS_record_.pdf"
        assert (archive_root / archived["archived_path"]).read_bytes() == b"example attachment"

        attachments = archive_source_attachments(
            archive_root,
            [
                {"filename": "notice.txt", "data": b"saved", "mime_type": "text/plain"},
                {"filename": "empty.txt", "data": b"", "mime_type": "text/plain"},
            ],
        )
        assert len(attachments) == 1
        assert attachments[0]["filename"] == "notice.txt"

        gmail_attachments = _extract_attachments(
            _GmailService(),
            {"id": "message-1", "payload": {"parts": [{"filename": "lab.pdf", "mimeType": "application/pdf", "body": {"attachmentId": "a1", "size": 5}}]}},
        )
        assert gmail_attachments == [{"filename": "lab.pdf", "mime_type": "application/pdf", "data": b"saved"}]
        classroom_attachments = _download_materials(
            _DriveService(), [{"driveFile": {"driveFile": {"id": "file-1"}}}]
        )
        assert classroom_attachments == [{"filename": "schedule.pdf", "mime_type": "application/pdf", "data": b"drive"}]

        database.DATABASE_PATH = root / "isolated-triage.db"
        database.initialize_database()
        item = database.create_item(
            "A file was attached.",
            {"category": "Obligation", "reason": "Test", "deadline": None, "mandatory": True},
            attachments=attachments,
            source="gmail",
            source_id="attachment-test",
        )
        assert item is not None and item["attachments"] == attachments
        newest = database.create_item(
            "A later manual item.",
            {"category": "Noise", "reason": "Test", "deadline": None, "mandatory": False},
            source="manual",
        )
        assert newest is not None
        assert database.get_recent_items()[0]["id"] == newest["id"]
        history = database.get_history_items(query="later", category="Noise", source="manual")
        assert [entry["id"] for entry in history] == [newest["id"]]
        assert database.get_history_items(status="done") == []
        listed = database.get_archived_attachments()
        assert len(listed) == 1 and listed[0]["archived_path"] == attachments[0]["archived_path"]
        del item, listed
        gc.collect()

    print("Attachment archive checks passed.")


if __name__ == "__main__":
    main()
