"""Shared read-only Google OAuth credential helpers for Triage sources."""

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/classroom.announcements.readonly",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
TOKEN_PATH = Path(__file__).with_name("token.json")


def get_google_credentials() -> Credentials:
    """Load and refresh the locally authorized Google credentials."""
    if not TOKEN_PATH.is_file():
        raise RuntimeError(
            "Google authorization has not been set up. Run python setup_google_auth.py "
            "from the backend directory first."
        )

    # Preserve the scope set Google actually granted at consent time. Some
    # Workspace domains return a narrower set than was requested.
    credentials = Credentials.from_authorized_user_file(TOKEN_PATH)
    if credentials.valid:
        return credentials
    if not credentials.expired or not credentials.refresh_token:
        raise RuntimeError(
            "Google authorization is invalid or cannot be refreshed. "
            "Run python setup_google_auth.py again."
        )

    credentials.refresh(Request())
    TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")
    return credentials
