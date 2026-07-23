"""Hosted Google OAuth, encrypted connections, and durable API sessions."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

try:
    from cryptography.fernet import Fernet
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import id_token
    from google_auth_oauthlib.flow import Flow
except ImportError:
    Fernet = None
    GoogleRequest = None
    id_token = None
    Flow = None

from google_client import GOOGLE_SCOPES

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "").rstrip("/")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
TOKEN_ENCRYPTION_KEY = os.getenv("OAUTH_TOKEN_ENCRYPTION_KEY", "").strip()
HOSTED_AUTH_ENABLED = os.getenv("HOSTED_AUTH_ENABLED", "").lower() == "true"
SESSION_LIFETIME_DAYS = 30
STATE_LIFETIME_MINUTES = 10


def is_enabled() -> bool:
    return HOSTED_AUTH_ENABLED


def configuration_error() -> str | None:
    if not HOSTED_AUTH_ENABLED:
        return None
    required = {
        "DATABASE_URL": DATABASE_URL,
        "FRONTEND_ORIGIN": FRONTEND_ORIGIN,
        "GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID,
        "GOOGLE_CLIENT_SECRET": GOOGLE_CLIENT_SECRET,
        "GOOGLE_REDIRECT_URI": GOOGLE_REDIRECT_URI,
        "OAUTH_TOKEN_ENCRYPTION_KEY": TOKEN_ENCRYPTION_KEY,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        return f"Hosted authentication is missing: {', '.join(missing)}."
    if not DATABASE_URL.startswith(("postgres://", "postgresql://")):
        return "Hosted authentication requires a PostgreSQL DATABASE_URL."
    if Fernet is None or Flow is None or id_token is None or GoogleRequest is None:
        return "Hosted authentication dependencies are not installed."
    try:
        Fernet(TOKEN_ENCRYPTION_KEY.encode("utf-8"))
    except (TypeError, ValueError):
        return "OAUTH_TOKEN_ENCRYPTION_KEY must be a valid Fernet key."
    return None


def initialize() -> None:
    """Create hosted-only account tables when the feature is configured."""
    if not HOSTED_AUTH_ENABLED:
        return
    error = configuration_error()
    if error:
        raise RuntimeError(error)
    with _connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY, google_subject TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL, display_name TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS google_connections (
                user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                encrypted_credentials BYTEA NOT NULL, scopes TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS api_sessions (
                token_hash TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS oauth_states (
                state_hash TEXT PRIMARY KEY, code_verifier TEXT NOT NULL, return_to TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)


def authorization_url(return_to: str | None) -> str:
    """Create a one-time, PKCE-protected Google authorization request."""
    _ensure_configured()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    target = _validated_return_to(return_to)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with _connection() as connection:
        connection.execute("DELETE FROM oauth_states WHERE expires_at < NOW()")
        connection.execute(
            "INSERT INTO oauth_states (state_hash, code_verifier, return_to, expires_at) VALUES (%s, %s, %s, %s)",
            (_hash(state), verifier, target, _utc_now() + timedelta(minutes=STATE_LIFETIME_MINUTES)),
        )
    flow = _flow()
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    return url


def complete_authorization(code: str, state: str) -> tuple[str, str]:
    """Validate callback state, store the connection, and create a durable session."""
    _ensure_configured()
    with _connection() as connection:
        state_row = connection.execute(
            "DELETE FROM oauth_states WHERE state_hash = %s AND expires_at > NOW() RETURNING code_verifier, return_to",
            (_hash(state),),
        ).fetchone()
    if not state_row:
        raise ValueError("Google sign-in expired or was already used. Please try again.")

    flow = _flow()
    flow.fetch_token(code=code, code_verifier=state_row["code_verifier"])
    credentials = flow.credentials
    if not credentials.id_token:
        raise ValueError("Google did not return an identity token. Please try again.")
    identity = id_token.verify_oauth2_token(credentials.id_token, GoogleRequest(), GOOGLE_CLIENT_ID)
    if not identity.get("email_verified") or not identity.get("sub") or not identity.get("email"):
        raise ValueError("Google did not provide a verified account identity.")

    with _connection() as connection:
        user = connection.execute(
            """
            INSERT INTO users (google_subject, email, display_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (google_subject) DO UPDATE
            SET email = EXCLUDED.email, display_name = EXCLUDED.display_name, updated_at = NOW()
            RETURNING id
            """,
            (identity["sub"], identity["email"], identity.get("name")),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO google_connections (user_id, encrypted_credentials, scopes)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
            SET encrypted_credentials = EXCLUDED.encrypted_credentials, scopes = EXCLUDED.scopes, updated_at = NOW()
            """,
            (user["id"], _fernet().encrypt(credentials.to_json().encode("utf-8")), " ".join(credentials.scopes or [])),
        )
        token = secrets.token_urlsafe(48)
        connection.execute(
            "INSERT INTO api_sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
            (_hash(token), user["id"], _utc_now() + timedelta(days=SESSION_LIFETIME_DAYS)),
        )
    return state_row["return_to"], token


def session_user(token: str) -> str | None:
    """Return the owning user ID for an unexpired hosted session."""
    if not HOSTED_AUTH_ENABLED:
        return None
    with _connection() as connection:
        row = connection.execute(
            "SELECT user_id FROM api_sessions WHERE token_hash = %s AND expires_at > NOW()",
            (_hash(token),),
        ).fetchone()
    return str(row["user_id"]) if row else None


def has_google_connection(owner_id: str) -> bool:
    if not HOSTED_AUTH_ENABLED:
        return False
    with _connection() as connection:
        return connection.execute("SELECT 1 FROM google_connections WHERE user_id = %s", (owner_id,)).fetchone() is not None


def credentials_json(owner_id: str) -> str | None:
    """Decrypt one user's Google credential payload for a read-only sync."""
    if not HOSTED_AUTH_ENABLED:
        return None
    with _connection() as connection:
        row = connection.execute(
            "SELECT encrypted_credentials FROM google_connections WHERE user_id = %s", (owner_id,)
        ).fetchone()
    if not row:
        return None
    return _fernet().decrypt(bytes(row["encrypted_credentials"])).decode("utf-8")


def save_credentials_json(owner_id: str, value: str) -> None:
    with _connection() as connection:
        connection.execute(
            "UPDATE google_connections SET encrypted_credentials = %s, updated_at = NOW() WHERE user_id = %s",
            (_fernet().encrypt(value.encode("utf-8")), owner_id),
        )


def _flow() -> Flow:
    if Flow is None:
        raise RuntimeError("Hosted authentication dependencies are not installed.")
    return Flow.from_client_config(
        {"web": {"client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
                  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                  "token_uri": "https://oauth2.googleapis.com/token"}},
        scopes=[*GOOGLE_SCOPES, "openid", "email", "profile"],
        redirect_uri=GOOGLE_REDIRECT_URI,
    )


def _validated_return_to(value: str | None) -> str:
    target = (value or FRONTEND_ORIGIN).rstrip("/")
    if _origin(target) != FRONTEND_ORIGIN:
        raise ValueError("Google sign-in must return to the configured frontend origin.")
    return target


def _origin(value: str) -> str:
    parsed = urlparse(value)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""


def _connection():
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def _fernet() -> Fernet:
    if Fernet is None:
        raise RuntimeError("Hosted authentication dependencies are not installed.")
    return Fernet(TOKEN_ENCRYPTION_KEY.encode("utf-8"))


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_configured() -> None:
    error = configuration_error()
    if error:
        raise RuntimeError(error)
