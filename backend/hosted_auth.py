"""Hosted Google OAuth, encrypted connections, and durable API sessions."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
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

try:
    from pywebpush import WebPushException, webpush
except ImportError:
    WebPushException = Exception
    webpush = None

from google_client import GOOGLE_SCOPES
from reminder_schedule import parse_deadline, reminder_window

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "").rstrip("/")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
TOKEN_ENCRYPTION_KEY = os.getenv("OAUTH_TOKEN_ENCRYPTION_KEY", "").strip()
HOSTED_AUTH_ENABLED = os.getenv("HOSTED_AUTH_ENABLED", "").lower() == "true"
SESSION_LIFETIME_DAYS = 30
STATE_LIFETIME_MINUTES = 10
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip()
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "").strip()
REMINDER_TIMEZONE = os.getenv("REMINDER_TIMEZONE", "UTC").strip() or "UTC"

# Google can return canonical equivalents of requested scopes. For example, it
# returns the userinfo URLs for the OpenID ``email`` and ``profile`` aliases.
# oauthlib treats that valid normalization as an exception unless this flag is
# set. Triage still stores the scopes Google actually granted and the Google
# APIs enforce those grants on every read-only source request.
if HOSTED_AUTH_ENABLED:
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


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


def push_configuration_error() -> str | None:
    """Return a safe explanation when durable push is not configured."""
    if not HOSTED_AUTH_ENABLED:
        return "Durable reminders require hosted authentication."
    missing = [
        name for name, value in {
            "VAPID_PUBLIC_KEY": VAPID_PUBLIC_KEY,
            "VAPID_PRIVATE_KEY": VAPID_PRIVATE_KEY,
            "VAPID_SUBJECT": VAPID_SUBJECT,
        }.items() if not value
    ]
    if missing:
        return f"Durable reminders are not configured ({', '.join(missing)} missing)."
    if webpush is None:
        return "Durable reminder dependency is not installed."
    try:
        ZoneInfo(REMINDER_TIMEZONE)
    except ZoneInfoNotFoundError:
        return "REMINDER_TIMEZONE must be a valid IANA timezone."
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
        connection.execute("""
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                endpoint_hash TEXT NOT NULL UNIQUE, encrypted_subscription BYTEA NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS reminder_deliveries (
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                reminder_window TEXT NOT NULL, reminder_date DATE NOT NULL,
                delivered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, reminder_window, reminder_date)
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


def revoke_session(token: str) -> None:
    """Invalidate just the current hosted API session without revoking Google access."""
    if not HOSTED_AUTH_ENABLED or not token:
        return
    with _connection() as connection:
        connection.execute("DELETE FROM api_sessions WHERE token_hash = %s", (_hash(token),))


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


def push_public_configuration(owner_id: str) -> dict[str, object]:
    """Expose only the public VAPID key and current opt-in state to its owner."""
    error = push_configuration_error()
    subscribed = False
    if HOSTED_AUTH_ENABLED:
        with _connection() as connection:
            subscribed = connection.execute(
                "SELECT 1 FROM push_subscriptions WHERE user_id = %s", (owner_id,)
            ).fetchone() is not None
    return {
        "enabled": error is None,
        "public_key": VAPID_PUBLIC_KEY if error is None else "",
        "subscribed": subscribed,
        "detail": error,
    }


def save_push_subscription(owner_id: str, subscription: dict[str, object]) -> None:
    """Encrypt one browser PushSubscription; endpoint contents never leave the server."""
    error = push_configuration_error()
    if error:
        raise RuntimeError(error)
    endpoint = subscription.get("endpoint") if isinstance(subscription, dict) else None
    keys = subscription.get("keys") if isinstance(subscription, dict) else None
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        raise ValueError("Push subscription must contain a secure browser endpoint.")
    if not isinstance(keys, dict) or not all(isinstance(keys.get(name), str) and keys[name] for name in ("p256dh", "auth")):
        raise ValueError("Push subscription is missing browser encryption keys.")
    encoded = json.dumps(subscription, separators=(",", ":"), sort_keys=True).encode("utf-8")
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO push_subscriptions (user_id, endpoint_hash, encrypted_subscription)
            VALUES (%s, %s, %s)
            ON CONFLICT (endpoint_hash) DO UPDATE
            SET user_id = EXCLUDED.user_id, encrypted_subscription = EXCLUDED.encrypted_subscription, updated_at = NOW()
            """,
            (owner_id, _hash(endpoint), _fernet().encrypt(encoded)),
        )


def remove_push_subscription(owner_id: str, endpoint: str) -> None:
    if not isinstance(endpoint, str) or not endpoint:
        raise ValueError("Push subscription endpoint is required.")
    with _connection() as connection:
        connection.execute(
            "DELETE FROM push_subscriptions WHERE user_id = %s AND endpoint_hash = %s",
            (owner_id, _hash(endpoint)),
        )


def dispatch_due_reminders(now: datetime | None = None) -> dict[str, int]:
    """Send one privacy-preserving today/tomorrow summary per opted-in user.

    This function is intentionally invoked by an authenticated scheduler, not
    by a browser request.  It only considers open obligations with explicit
    parseable dates and never includes obligation text in push payloads.
    """
    error = push_configuration_error()
    if error:
        raise RuntimeError(error)
    local_now = (now or _utc_now()).astimezone(ZoneInfo(REMINDER_TIMEZONE))
    today = local_now.date()
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT i.id, i.owner_id, i.deadline
            FROM items AS i
            JOIN push_subscriptions AS p ON p.user_id = i.owner_id::BIGINT
            WHERE i.category = 'Obligation' AND i.status = 'open' AND i.deadline IS NOT NULL
            """
        ).fetchall()

    due_by_user: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        window = reminder_window(parse_deadline(row["deadline"], today), today)
        if window:
            due_by_user.setdefault((str(row["owner_id"]), window), []).append(row)

    sent = 0
    skipped = 0
    for (owner_id, window), due_items in due_by_user.items():
        if not _claim_reminder_delivery(owner_id, window, today):
            skipped += 1
            continue
        delivered = _send_reminder_to_subscriptions(owner_id, window, len(due_items))
        if delivered:
            sent += delivered
        else:
            _release_reminder_delivery(owner_id, window, today)
    return {"sent": sent, "skipped": skipped, "eligible_users": len(due_by_user)}


def _claim_reminder_delivery(owner_id: str, window: str, reminder_date) -> bool:
    with _connection() as connection:
        row = connection.execute(
            """
            INSERT INTO reminder_deliveries (user_id, reminder_window, reminder_date)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING user_id
            """,
            (owner_id, window, reminder_date),
        ).fetchone()
    return row is not None


def _release_reminder_delivery(owner_id: str, window: str, reminder_date) -> None:
    with _connection() as connection:
        connection.execute(
            "DELETE FROM reminder_deliveries WHERE user_id = %s AND reminder_window = %s AND reminder_date = %s",
            (owner_id, window, reminder_date),
        )


def _send_reminder_to_subscriptions(owner_id: str, window: str, item_count: int) -> int:
    with _connection() as connection:
        rows = connection.execute(
            "SELECT id, encrypted_subscription FROM push_subscriptions WHERE user_id = %s", (owner_id,)
        ).fetchall()
    payload = json.dumps({
        "title": "Triage deadline reminder",
        "body": f"{item_count} obligation{' is' if item_count == 1 else 's are'} due {window}. Open Triage to review.",
        "url": FRONTEND_ORIGIN,
    })
    delivered = 0
    for row in rows:
        try:
            subscription = json.loads(_fernet().decrypt(bytes(row["encrypted_subscription"])).decode("utf-8"))
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUBJECT},
            )
            delivered += 1
        except WebPushException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in (404, 410):
                with _connection() as connection:
                    connection.execute("DELETE FROM push_subscriptions WHERE id = %s", (row["id"],))
        except (ValueError, TypeError, json.JSONDecodeError):
            # A corrupt or obsolete subscription is removed; no item data is exposed.
            with _connection() as connection:
                connection.execute("DELETE FROM push_subscriptions WHERE id = %s", (row["id"],))
        except Exception:
            # Temporary provider/network failure: retain the subscription and
            # release the delivery claim so the next scheduled run can retry.
            continue
    return delivered


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
