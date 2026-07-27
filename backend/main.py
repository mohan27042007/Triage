"""FastAPI server for the local-first Triage classification and Action Queue."""

import os
import secrets
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from dotenv import load_dotenv
from oauthlib.oauth2.rfc6749.errors import OAuth2Error

load_dotenv()

from attachment_archive import (
    MAX_ARCHIVE_BYTES,
    archive_attachment,
    archived_file_exists,
    original_filename_from_archive,
    read_archived_file,
)
from assignment_helper import scaffold_assignment
from classifier import (
    build_study_plan,
    classify,
    draft_poll_or_form_response,
    draft_routine_form_response,
)
from document_ingestion import extract_document_text
from google_client import TOKEN_PATH
from hosted_auth import (
    authorization_url,
    complete_authorization,
    configuration_error as hosted_auth_configuration_error,
    dispatch_due_reminders,
    has_google_connection,
    initialize as initialize_hosted_auth,
    is_enabled as hosted_auth_enabled,
    push_public_configuration,
    remove_push_subscription,
    revoke_session,
    save_push_subscription,
    session_user,
    workspace_for_user,
)
from rate_limit import RateLimiter
from reminder_schedule import parse_deadline
from source_ingestion import ingest_source_changes
from whatsapp_demo_data import WHATSAPP_DEMO_MESSAGES, WHATSAPP_DEMO_SOURCE
from database import (
    create_assignment_help,
    create_item,
    create_pending_action,
    enable_source_connection,
    approve_pending_action,
    get_item,
    get_item_by_source_id,
    has_items_from_source,
    get_assignment_history,
    get_archived_attachments,
    export_owner_data,
    get_open_obligations,
    get_history_items,
    get_recent_items,
    get_pending_actions,
    get_source_sync_status,
    get_source_connections,
    get_study_plan,
    initialize_database,
    is_source_connection_paused,
    record_source_connection_outcome,
    reject_pending_action,
    record_source_sync,
    replace_study_plan,
    set_source_connection_state,
    DEFAULT_OWNER_ID,
)

app = FastAPI(title="Triage API", version="0.1.0")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "")
VALID_SESSION_TOKENS: set[str] = set()
ARCHIVE_DIRECTORY = Path(__file__).with_name("archive")
MAX_CLASSIFICATION_TEXT_CHARS = 5_000
MAX_STUDY_DOCUMENT_TEXT_CHARS = 30_000
DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]
REMINDER_DISPATCH_SECRET = os.getenv("REMINDER_DISPATCH_SECRET", "").strip()
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "").lower() == "true"
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "false"
RATE_LIMITER = RateLimiter()

initialize_database()
initialize_hosted_auth()


@app.middleware("http")
async def require_demo_auth(request: Request, call_next):
    """Require an in-memory demo token for all non-public API routes."""
    public_paths = {
        "/health", "/auth/login", "/auth/config", "/auth/google/start", "/auth/google/callback",
        "/internal/reminders/dispatch",
    }
    if request.method == "OPTIONS":
        return await call_next(request)

    if request.url.path in public_paths:
        if not _allow_request(request, _public_rate_limit(request.url.path)):
            return _too_many_requests()
        return await call_next(request)

    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return JSONResponse(status_code=401, content={"detail": "Authentication required."})
    if hosted_auth_enabled():
        owner_id = session_user(token)
        if not owner_id:
            return JSONResponse(status_code=401, content={"detail": "Authentication required."})
        request.state.owner_id = owner_id
        workspace_id = workspace_for_user(owner_id)
        if workspace_id is None:
            return JSONResponse(status_code=503, content={"detail": "Workspace setup is incomplete. Please try again."})
        request.state.workspace_id = workspace_id
        request.state.session_token = token
        if not _allow_request(request, _authenticated_rate_limit(request.url.path), owner_id):
            return _too_many_requests()
        return await call_next(request)
    if token not in VALID_SESSION_TOKENS:
        return JSONResponse(status_code=401, content={"detail": "Authentication required."})
    request.state.owner_id = DEFAULT_OWNER_ID
    request.state.workspace_id = None
    request.state.session_token = token
    if not _allow_request(request, _authenticated_rate_limit(request.url.path), DEFAULT_OWNER_ID):
        return _too_many_requests()
    return await call_next(request)


@app.middleware("http")
async def add_hardening_headers(request: Request, call_next):
    """Avoid caching private API output and set baseline browser protections."""
    response = await call_next(request)
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _client_key(request: Request) -> str:
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


def _public_rate_limit(path: str) -> tuple[int, int] | None:
    if path == "/auth/login":
        return (10, 15 * 60)
    if path == "/auth/google/start":
        return (20, 15 * 60)
    if path == "/internal/reminders/dispatch":
        return (5, 60)
    return None


def _authenticated_rate_limit(path: str) -> tuple[int, int] | None:
    if path in {"/ingest", "/study/upload", "/assignment/help"}:
        return (20, 10 * 60)
    if path in {"/sources/gmail/sync", "/sources/classroom/sync", "/sources/whatsapp/demo-load"}:
        return (10, 10 * 60)
    if path in {"/push/subscribe", "/auth/logout"}:
        return (10, 10 * 60)
    return None


def _allow_request(request: Request, limit: tuple[int, int] | None, owner_id: str | None = None) -> bool:
    if not RATE_LIMIT_ENABLED or limit is None:
        return True
    scope = owner_id or _client_key(request)
    return RATE_LIMITER.allow(f"{request.url.path}:{scope}", *limit)


def _too_many_requests() -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please wait a moment and try again."},
        headers={"Retry-After": "60"},
    )


@app.post("/auth/login")
async def login(request: Request) -> dict[str, str]:
    """Issue an in-memory token after validating the shared demo password."""
    if hosted_auth_enabled():
        raise HTTPException(status_code=403, detail="Use Google sign-in for this hosted deployment.")
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(status_code=400, detail='Use application/json with {"password": "..."}.')
    if not DEMO_PASSWORD:
        raise HTTPException(status_code=503, detail="DEMO_PASSWORD is not configured.")

    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("password"), str):
        raise HTTPException(status_code=400, detail='JSON requests must use {"password": "..."}.')
    if not secrets.compare_digest(payload["password"], DEMO_PASSWORD):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    token = secrets.token_hex(32)
    VALID_SESSION_TOKENS.add(token)
    return {"token": token}


@app.post("/auth/logout")
def logout(request: Request) -> Response:
    """End the current app session; local Google tokens stay untouched."""
    token = getattr(request.state, "session_token", "")
    if hosted_auth_enabled():
        revoke_session(token)
    else:
        VALID_SESSION_TOKENS.discard(token)
    return Response(status_code=204)


@app.get("/account/export")
def export_account_data(request: Request) -> JSONResponse:
    """Download the signed-in student's data metadata without exposing archive bytes."""
    exported = export_owner_data(request.state.owner_id)
    return JSONResponse(
        content=exported,
        headers={"Content-Disposition": 'attachment; filename="triage-data-export.json"'},
    )


@app.get("/auth/config")
def auth_config() -> dict[str, bool]:
    """Let the frontend show hosted Google sign-in only when it is configured."""
    return {"hosted_auth": hosted_auth_enabled() and hosted_auth_configuration_error() is None}


@app.get("/auth/google/start")
def start_google_auth(return_to: str | None = None) -> RedirectResponse:
    """Redirect a hosted user into the read-only Google consent flow."""
    try:
        return RedirectResponse(authorization_url(return_to), status_code=302)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/auth/google/callback")
def google_auth_callback(code: str = "", state: str = "") -> RedirectResponse:
    """Exchange the verified callback and return a fragment-only API session token."""
    if not code or not state:
        raise HTTPException(status_code=400, detail="Google sign-in did not return code and state.")
    try:
        return_to, token = complete_authorization(code, state)
    except (RuntimeError, ValueError, OAuth2Error) as exc:
        raise HTTPException(status_code=400, detail=f"Google sign-in could not be completed: {exc}") from exc
    return RedirectResponse(f"{return_to}#oauth_token={token}", status_code=303)


@app.get("/push/config")
def push_config(request: Request) -> dict:
    """Return opt-in state and public VAPID material for this signed-in user."""
    return push_public_configuration(request.state.owner_id)


@app.post("/push/subscribe")
async def subscribe_push(request: Request) -> dict[str, bool]:
    """Save an encrypted browser subscription for the current hosted user."""
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(status_code=400, detail="Use application/json with a browser PushSubscription.")
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("Push subscription must be a JSON object.")
        save_push_subscription(request.state.owner_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"subscribed": True}


@app.delete("/push/subscribe")
async def unsubscribe_push(request: Request) -> Response:
    try:
        payload = await request.json()
        endpoint = payload.get("endpoint") if isinstance(payload, dict) else None
        remove_push_subscription(request.state.owner_id, endpoint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=204)


@app.post("/internal/reminders/dispatch")
def dispatch_reminders(request: Request) -> dict[str, int]:
    """Run by a trusted schedule; it never accepts a browser session token."""
    supplied_secret = request.headers.get("X-Reminder-Secret", "")
    if not REMINDER_DISPATCH_SECRET or not secrets.compare_digest(supplied_secret, REMINDER_DISPATCH_SECRET):
        raise HTTPException(status_code=401, detail="Invalid reminder dispatch credentials.")
    try:
        return dispatch_due_reminders()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/ingest")
async def ingest(request: Request) -> dict:
    """Accept pasted text or one TXT, selectable-text PDF, or DOCX upload."""
    content_type = request.headers.get("content-type", "")

    try:
        if content_type.startswith("application/json"):
            payload = await request.json()
            if not isinstance(payload, dict) or not isinstance(
                payload.get("text"), str
            ):
                raise ValueError('JSON requests must use {"text": "..."}.')
            text = payload["text"]
        elif content_type.startswith("multipart/form-data"):
            form = await request.form()
            uploaded_file = form.get("file")
            if not hasattr(uploaded_file, "filename") or not uploaded_file.filename:
                raise ValueError("Upload a TXT, PDF, or DOCX file using the 'file' field.")
            text, archived_path = await _read_and_archive_text_upload(
                uploaded_file, "file", request.state.owner_id
            )
        else:
            raise ValueError("Use application/json or multipart/form-data.")

        if len(text) > MAX_CLASSIFICATION_TEXT_CHARS:
            raise ValueError(f"Text is too long for classification ({MAX_CLASSIFICATION_TEXT_CHARS:,} characters maximum).")

        classification = classify(text)
        return create_item(
            text,
            classification,
            archived_path if content_type.startswith("multipart/form-data") else None,
            owner_id=request.state.owner_id,
            workspace_id=request.state.workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/queue")
def queue(request: Request) -> dict[str, list[dict]]:
    """Return open obligations grouped by the attention they need."""
    grouped: dict[str, list[dict]] = {"Immediate": [], "This Week": [], "Later": []}
    for item in get_open_obligations(request.state.owner_id):
        grouped[_queue_group(item)].append(item)
    return grouped


@app.get("/stream")
def stream(request: Request) -> dict[str, list[dict]]:
    """Return the latest classified items across manual and connected sources."""
    return {"items": get_recent_items(owner_id=request.state.owner_id)}


@app.get("/history")
def history(request: Request,
    query: str = "", category: str = "", source: str = "", status: str = ""
) -> dict[str, list[dict]]:
    """Search the local classification history without changing any item."""
    return {"items": get_history_items(query, category, source, status, owner_id=request.state.owner_id)}


@app.get("/sources/google/status")
def google_source_status(request: Request) -> dict[str, bool]:
    """Report whether the local Google OAuth setup has completed."""
    return {"authorized": has_google_connection(request.state.owner_id) if hosted_auth_enabled() else TOKEN_PATH.is_file()}


@app.get("/sources/status")
def source_status(request: Request) -> dict[str, object]:
    """Return saved outcomes for user-requested Google source syncs.

    Connection availability comes from the stored read-only Google grant; this
    endpoint does not perform an external health check or trigger a sync.
    """
    authorized = has_google_connection(request.state.owner_id) if hosted_auth_enabled() else TOKEN_PATH.is_file()
    return {
        "google_authorized": authorized,
        "sources": get_source_sync_status(request.state.owner_id),
        "connections": get_source_connections(request.state.owner_id),
    }


@app.post("/sources/{source}/connection/enable")
async def enable_connection(source: str, request: Request) -> dict:
    """Save an enabled read-only Google source connection for this workspace."""
    if source not in {"gmail", "classroom"}:
        raise HTTPException(status_code=404, detail="Unsupported source connection.")
    authorized = has_google_connection(request.state.owner_id) if hosted_auth_enabled() else TOKEN_PATH.is_file()
    if not authorized:
        raise HTTPException(status_code=409, detail="Connect Google before enabling this source.")
    payload: dict = {}
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            received = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body.") from exc
        if not isinstance(received, dict):
            raise HTTPException(status_code=400, detail="Connection settings must be a JSON object.")
        payload = received
    try:
        return enable_source_connection(
            source,
            f"google-connection:{request.state.owner_id}" if hosted_auth_enabled() else "local-google-token",
            owner_id=request.state.owner_id,
            workspace_id=request.state.workspace_id,
            selected_channels=payload.get("selected_channels"),
            sync_interval_minutes=payload.get("sync_interval_minutes", 30),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/sources/{source}/connection/pause")
def pause_connection(source: str, request: Request) -> dict:
    """Pause a source without deleting its provider configuration or health history."""
    try:
        connection = set_source_connection_state(source, "paused", owner_id=request.state.owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if connection is None:
        raise HTTPException(status_code=404, detail="Source connection not found.")
    return connection


@app.post("/sources/gmail/sync")
def sync_gmail(request: Request) -> dict[str, int]:
    """Classify new inbox messages while preserving Gmail IDs for deduplication."""
    return _sync_source("gmail", "Gmail", request)


@app.post("/sources/classroom/sync")
def sync_classroom(request: Request) -> dict[str, int]:
    """Classify new Classroom items while preserving IDs for deduplication."""
    return _sync_source("classroom", "Google Classroom", request)


def _sync_source(source: str, display_name: str, request: Request) -> dict[str, int]:
    """Preserve current manual sync behavior while collecting through one connector."""
    if is_source_connection_paused(source, owner_id=request.state.owner_id):
        raise HTTPException(status_code=409, detail=f"{display_name} is paused. Resume it before syncing.")
    try:
        outcome = ingest_source_changes(
            source,
            owner_id=request.state.owner_id,
            workspace_id=request.state.workspace_id,
            archive_directory=ARCHIVE_DIRECTORY,
        )
        record_source_sync(source, succeeded=True, imported_count=outcome["processed"], owner_id=request.state.owner_id, workspace_id=request.state.workspace_id)
        record_source_connection_outcome(source, succeeded=True, owner_id=request.state.owner_id)
        return {"processed": outcome["processed"], "skipped": outcome["skipped"]}
    except RuntimeError as exc:
        error_message = f"The {display_name} sync could not finish. Retry when ready."
        record_source_sync(source, succeeded=False, error_message=error_message, owner_id=request.state.owner_id, workspace_id=request.state.workspace_id)
        record_source_connection_outcome(source, succeeded=False, error_message=error_message, owner_id=request.state.owner_id)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/sources/whatsapp/demo-load")
def load_whatsapp_demo_data(request: Request) -> dict[str, int | bool | str]:
    """Classify and persist the representative, non-live WhatsApp demo messages."""
    if has_items_from_source(WHATSAPP_DEMO_SOURCE, request.state.owner_id):
        return {
            "processed": 0,
            "already_loaded": True,
            "message": "WhatsApp demo data is already loaded.",
        }

    try:
        for index, message in enumerate(WHATSAPP_DEMO_MESSAGES, start=1):
            create_item(
                message,
                classify(message),
                source=WHATSAPP_DEMO_SOURCE,
                source_id=f"whatsapp-demo-{index}",
                owner_id=request.state.owner_id,
                workspace_id=request.state.workspace_id,
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "processed": len(WHATSAPP_DEMO_MESSAGES),
        "already_loaded": False,
        "message": f"Loaded {len(WHATSAPP_DEMO_MESSAGES)} simulated WhatsApp messages.",
    }


@app.post("/queue/{item_id}/done")
def request_queue_item_completion(item_id: int, request: Request) -> dict:
    """Request human approval before marking one queue item done."""
    item = get_item(item_id, request.state.owner_id)
    if not item or item["category"] != "Obligation" or item["status"] != "open":
        raise HTTPException(status_code=404, detail="Open queue item not found.")
    payload = {
        "message": f"Mark '{item['text'][:120]}' as done?",
        "item_text": item["text"],
    }
    if item.get("is_poll_or_form"):
        drafted_response = draft_poll_or_form_response(item["text"])
        if drafted_response:
            payload["drafted_response"] = drafted_response
    return create_pending_action(
        item_id=item_id,
        action_type="mark_done",
        payload=payload,
        owner_id=request.state.owner_id,
        workspace_id=request.state.workspace_id,
    )


@app.post("/queue/{item_id}/form-draft")
def request_form_draft(item_id: int, request: Request) -> dict:
    """Stage a copy-only routine-form draft without marking an obligation complete."""
    item = get_item(item_id, request.state.owner_id)
    if not item or item["category"] != "Obligation" or item["status"] != "open":
        raise HTTPException(status_code=404, detail="Open queue item not found.")

    draft = draft_routine_form_response(item["text"])
    if not draft:
        raise HTTPException(
            status_code=400,
            detail="This item does not name supported routine form fields.",
        )
    return create_pending_action(
        item_id=item_id,
        action_type="prepare_form_draft",
        payload={
            "message": f"Review a copy-only form draft for '{item['text'][:120]}'.",
            "item_text": item["text"],
            "form_fields": draft["fields"],
        },
        owner_id=request.state.owner_id,
        workspace_id=request.state.workspace_id,
    )


@app.get("/pending")
def pending_actions(request: Request) -> dict[str, list[dict]]:
    """List actions that require a student's decision."""
    return {"actions": get_pending_actions(request.state.owner_id)}


@app.post("/pending/{action_id}/approve")
def approve_action(action_id: int, request: Request) -> dict:
    """Approve a pending action and apply its underlying local change."""
    try:
        action = approve_pending_action(action_id, request.state.owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not action:
        raise HTTPException(status_code=404, detail="Pending action not found or no longer applicable.")
    return action


@app.post("/pending/{action_id}/reject")
def reject_action(action_id: int, request: Request) -> dict:
    """Reject a pending action without applying its underlying change."""
    action = reject_pending_action(action_id, request.state.owner_id)
    if not action:
        raise HTTPException(status_code=404, detail="Pending action not found.")
    return action


@app.post("/study/upload")
async def upload_study_materials(request: Request) -> dict[str, list[dict]]:
    """Build a topic-ranked plan from two TXT, PDF, or DOCX study documents."""
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise HTTPException(status_code=400, detail="Use multipart/form-data with both study files.")

    try:
        form = await request.form()
        question_bank, question_bank_archived_path = await _read_and_archive_text_upload(
            form.get("question_bank"), "question_bank", request.state.owner_id, MAX_STUDY_DOCUMENT_TEXT_CHARS
        )
        unit_notes, unit_notes_archived_path = await _read_and_archive_text_upload(
            form.get("unit_notes"), "unit_notes", request.state.owner_id, MAX_STUDY_DOCUMENT_TEXT_CHARS
        )
        topics = build_study_plan(question_bank, unit_notes)
        return {
            "topics": replace_study_plan(
                topics, question_bank_archived_path, unit_notes_archived_path,
                request.state.owner_id, request.state.workspace_id,
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/study/plan")
def study_plan(request: Request) -> dict[str, list[dict]]:
    """Return the persisted, highest-priority-first study topics."""
    return {"topics": get_study_plan(request.state.owner_id)}


@app.get("/archive")
def list_archive(request: Request) -> dict[str, list[dict]]:
    """List the caller's retained files that are still available to download."""
    try:
        attachments = [
            attachment for attachment in get_archived_attachments(request.state.owner_id)
            if archived_file_exists(ARCHIVE_DIRECTORY, attachment["archived_path"], request.state.owner_id)
        ]
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"attachments": attachments}


@app.get("/archive/{filename}")
def download_archive(filename: str, request: Request) -> Response:
    """Serve one owner-scoped archived attachment without public storage URLs."""
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid archive filename.")
    if filename not in {attachment["archived_path"] for attachment in get_archived_attachments(request.state.owner_id)}:
        raise HTTPException(status_code=404, detail="Archived file not found.")
    try:
        archived_bytes = read_archived_file(ARCHIVE_DIRECTORY, filename, request.state.owner_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if archived_bytes is None:
        raise HTTPException(status_code=404, detail="Archived file not found.")
    download_name = original_filename_from_archive(filename).replace('"', "")
    return Response(
        content=archived_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


@app.post("/assignment/help")
async def assignment_help(request: Request) -> dict:
    """Create and store a planning-only scaffold for one assignment prompt."""
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(status_code=400, detail='Use application/json with {"prompt": "..."}.')

    try:
        payload = await request.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("prompt"), str):
            raise ValueError('JSON requests must use {"prompt": "..."}.')
        prompt = payload["prompt"]
        if len(prompt) > 5000:
            raise ValueError("Assignment prompt is too long.")
        scaffold = scaffold_assignment(prompt)
        saved_scaffold = create_assignment_help(
            prompt, scaffold, request.state.owner_id, request.state.workspace_id
        )
        if not saved_scaffold:
            raise RuntimeError("Could not save the assignment scaffold.")
        return saved_scaffold
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/assignment/history")
def assignment_history(request: Request) -> dict[str, list[dict]]:
    """Return saved assignment scaffolds, newest first."""
    return {"assignments": get_assignment_history(request.state.owner_id)}


def _queue_group(item: dict) -> str:
    """Assign a queue group without guessing when a model deadline is unclear."""
    deadline_date = parse_deadline(item.get("deadline"))
    if deadline_date is None:
        return "Immediate" if item.get("mandatory") else "Later"

    today = date.today()
    if deadline_date <= today + timedelta(days=1):
        return "Immediate"

    end_of_week = today + timedelta(days=6 - today.weekday())
    return "This Week" if deadline_date <= end_of_week else "Later"


async def _read_and_archive_text_upload(
    uploaded_file: object,
    field_name: str,
    owner_id: str = DEFAULT_OWNER_ID,
    max_text_chars: int = MAX_CLASSIFICATION_TEXT_CHARS,
) -> tuple[str, str]:
    """Validate, archive, and extract bounded text from one supported upload."""
    if not hasattr(uploaded_file, "filename") or not hasattr(uploaded_file, "read"):
        raise ValueError(f"Upload a TXT, PDF, or DOCX file using the '{field_name}' field.")
    if not uploaded_file.filename:
        raise ValueError(f"Upload a TXT, PDF, or DOCX file using the '{field_name}' field.")
    try:
        file_bytes = await uploaded_file.read()
        if len(file_bytes) > MAX_ARCHIVE_BYTES:
            raise ValueError(f"The '{field_name}' file exceeds the 20 MB archive limit.")
        text, mime_type = extract_document_text(uploaded_file.filename, file_bytes, max_text_chars)
    except ValueError as exc:
        raise ValueError(f"The '{field_name}' file could not be used: {exc}") from exc
    archived = archive_attachment(ARCHIVE_DIRECTORY, uploaded_file.filename, file_bytes, mime_type, owner_id)
    if not archived:
        raise ValueError(f"The '{field_name}' file is empty or exceeds the 20 MB archive limit.")
    return text, archived["archived_path"]
