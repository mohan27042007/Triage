"""Shared read-only Google OAuth credential helpers for Triage sources."""

import json
import os
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


def get_google_credentials(owner_id: str | None = None) -> Credentials:
    """Load user-scoped hosted credentials or retain the local desktop fallback."""
    if os.getenv("HOSTED_AUTH_ENABLED", "").lower() == "true":
        if not owner_id:
            raise RuntimeError("A hosted Google sync requires an authenticated user.")
        from hosted_auth import credentials_json, save_credentials_json

        stored = credentials_json(owner_id)
        if not stored:
            raise RuntimeError("Connect your Google account before syncing this source.")
        credentials = Credentials.from_authorized_user_info(json.loads(stored))
        if credentials.valid:
            return credentials
        if not credentials.expired or not credentials.refresh_token:
            raise RuntimeError("Your Google connection expired. Connect it again to continue.")
        credentials.refresh(Request())
        save_credentials_json(owner_id, credentials.to_json())
        return credentials

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
