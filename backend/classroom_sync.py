"""Read Classroom notices and retain files attached through Google Drive."""

from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from attachment_archive import MAX_ARCHIVE_BYTES
from google_client import get_google_credentials


def fetch_recent_classroom_items(
    max_courses: int = 10, max_announcements_per_course: int = 5, owner_id: str | None = None
) -> list[dict[str, Any]]:
    """Return recent active-course items with any attached Drive files."""
    credentials = get_google_credentials(owner_id)
    service = build(
        "classroom", "v1", credentials=credentials, cache_discovery=False
    )
    drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    courses_response = service.courses().list(
        courseStates=["ACTIVE"], pageSize=max_courses
    ).execute()

    items: list[dict[str, str]] = []
    for course in courses_response.get("courses", []):
        course_id = course["id"]
        course_name = course.get("name", "Untitled course")
        announcements = service.courses().announcements().list(
            courseId=course_id,
            pageSize=max_announcements_per_course,
            orderBy="updateTime desc",
        ).execute()
        for announcement in announcements.get("announcements", []):
            text = announcement.get("text", "").strip()
            attachments = _download_materials(drive_service, announcement.get("materials", []))
            if text or attachments:
                items.append(
                    {
                        "id": _source_id("announcement", course_id, announcement["id"]),
                        "text": _with_course_context(course_name, _with_attachment_names(text, attachments)),
                        "attachments": attachments,
                    }
                )

        coursework = service.courses().courseWork().list(
            courseId=course_id,
            pageSize=max_announcements_per_course,
            orderBy="updateTime desc",
        ).execute()
        for work in coursework.get("courseWork", []):
            text = _coursework_text(work)
            attachments = _download_materials(drive_service, work.get("materials", []))
            if text or attachments:
                items.append(
                    {
                        "id": _source_id("coursework", course_id, work["id"]),
                        "text": _with_course_context(course_name, _with_attachment_names(text, attachments)),
                        "attachments": attachments,
                    }
                )
    return items


def _with_course_context(course_name: str, text: str) -> str:
    return f"[{course_name}] {text}"


def _source_id(item_type: str, course_id: str, item_id: str) -> str:
    """Make a stable globally unique source ID from a per-course resource ID."""
    return f"classroom:{item_type}:{course_id}:{item_id}"


def _coursework_text(work: dict[str, Any]) -> str:
    """Combine the most useful coursework fields into one classifier input."""
    parts = [work.get("title", "").strip(), work.get("description", "").strip()]
    return "\n".join(part for part in parts if part)


def _with_attachment_names(text: str, attachments: list[dict[str, Any]]) -> str:
    names = ", ".join(attachment["filename"] for attachment in attachments)
    return f"{text}\nAttachments: {names}".strip() if names else text


def _download_materials(drive_service: Any, materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy Classroom Drive-file materials into memory for local archiving.

    Links, videos, and Forms remain links in Classroom; only attached Drive files
    are copied because Triage's archive must contain an actual local file.
    """
    attachments: list[dict[str, Any]] = []
    for material in materials or []:
        resource = material.get("driveFile", {}).get("driveFile", {})
        file_id = resource.get("id")
        if not file_id:
            continue
        try:
            metadata = drive_service.files().get(
                fileId=file_id, fields="id,name,mimeType,size"
            ).execute()
            if int(metadata.get("size") or 0) > MAX_ARCHIVE_BYTES:
                continue
            mime_type = metadata.get("mimeType", "application/octet-stream")
            filename = metadata.get("name") or resource.get("title") or "classroom-attachment"
            if mime_type.startswith("application/vnd.google-apps."):
                data = drive_service.files().export(fileId=file_id, mimeType="application/pdf").execute()
                filename = f"{filename}.pdf" if not filename.lower().endswith(".pdf") else filename
                mime_type = "application/pdf"
            else:
                data = drive_service.files().get_media(fileId=file_id).execute()
        except HttpError:
            # Existing Classroom text sync still succeeds if a linked Drive file
            # is unavailable or the student has not re-authorized the new scope.
            continue
        if data:
            attachments.append({"filename": filename, "mime_type": mime_type, "data": data})
    return attachments
