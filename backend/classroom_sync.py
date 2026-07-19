"""Read recent Google Classroom announcements and coursework."""

from typing import Any

from googleapiclient.discovery import build

from google_client import get_google_credentials


def fetch_recent_classroom_items(
    max_courses: int = 10, max_announcements_per_course: int = 5
) -> list[dict[str, str]]:
    """Return recent active-course items with their course context included."""
    service = build(
        "classroom", "v1", credentials=get_google_credentials(), cache_discovery=False
    )
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
            if text:
                items.append(
                    {
                        "id": _source_id("announcement", course_id, announcement["id"]),
                        "text": _with_course_context(course_name, text),
                    }
                )

        coursework = service.courses().courseWork().list(
            courseId=course_id,
            pageSize=max_announcements_per_course,
            orderBy="updateTime desc",
        ).execute()
        for work in coursework.get("courseWork", []):
            text = _coursework_text(work)
            if text:
                items.append(
                    {
                        "id": _source_id("coursework", course_id, work["id"]),
                        "text": _with_course_context(course_name, text),
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
