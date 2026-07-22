"""FastAPI server for the local-first Triage classification and Action Queue."""

import os
import re
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv

from attachment_archive import (
    archive_attachment,
    archive_source_attachments,
    original_filename_from_archive,
)
from assignment_helper import scaffold_assignment
from classifier import (
    build_study_plan,
    classify,
    draft_poll_or_form_response,
    draft_routine_form_response,
)
from classroom_sync import fetch_recent_classroom_items
from gmail_sync import fetch_recent_gmail_messages
from google_client import TOKEN_PATH
from whatsapp_demo_data import WHATSAPP_DEMO_MESSAGES, WHATSAPP_DEMO_SOURCE
from database import (
    create_assignment_help,
    create_item,
    create_pending_action,
    approve_pending_action,
    get_item,
    get_item_by_source_id,
    has_items_from_source,
    get_assignment_history,
    get_archived_attachments,
    get_open_obligations,
    get_pending_actions,
    get_study_plan,
    initialize_database,
    reject_pending_action,
    replace_study_plan,
)

load_dotenv()

app = FastAPI(title="Triage API", version="0.1.0")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "")
VALID_SESSION_TOKENS: set[str] = set()
ARCHIVE_DIRECTORY = Path(__file__).with_name("archive")
DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]

initialize_database()


@app.middleware("http")
async def require_demo_auth(request: Request, call_next):
    """Require an in-memory demo token for all non-public API routes."""
    if request.method == "OPTIONS" or request.url.path in {"/health", "/auth/login"}:
        return await call_next(request)

    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token not in VALID_SESSION_TOKENS:
        return JSONResponse(status_code=401, content={"detail": "Authentication required."})
    return await call_next(request)


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


@app.post("/auth/login")
async def login(request: Request) -> dict[str, str]:
    """Issue an in-memory token after validating the shared demo password."""
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


@app.post("/ingest")
async def ingest(request: Request) -> dict:
    """Accept pasted JSON text or one UTF-8 .txt upload and classify it."""
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
                raise ValueError(
                    "Upload a .txt file using the 'file' field."
                )
            if Path(uploaded_file.filename).suffix.lower() != ".txt":
                raise ValueError(
                    "Only .txt files are supported in this local-first slice."
                )
            text, archived_path = await _read_and_archive_text_upload(uploaded_file, "file")
        else:
            raise ValueError("Use application/json or multipart/form-data.")

        if len(text) > 5000:
            raise ValueError("Text is too long for classification.")

        classification = classify(text)
        return create_item(
            text,
            classification,
            archived_path if content_type.startswith("multipart/form-data") else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/queue")
def queue() -> dict[str, list[dict]]:
    """Return open obligations grouped by the attention they need."""
    grouped: dict[str, list[dict]] = {"Immediate": [], "This Week": [], "Later": []}
    for item in get_open_obligations():
        grouped[_queue_group(item)].append(item)
    return grouped


@app.get("/sources/google/status")
def google_source_status() -> dict[str, bool]:
    """Report whether the local Google OAuth setup has completed."""
    return {"authorized": TOKEN_PATH.is_file()}


@app.post("/sources/gmail/sync")
def sync_gmail() -> dict[str, int]:
    """Classify new inbox messages while preserving Gmail IDs for deduplication."""
    try:
        messages = fetch_recent_gmail_messages()
        processed = 0
        skipped = 0
        for message in messages:
            if get_item_by_source_id(message["id"]):
                skipped += 1
                continue
            create_item(
                message["text"],
                classify(message["text"]),
                attachments=archive_source_attachments(ARCHIVE_DIRECTORY, message.get("attachments")),
                source="gmail",
                source_id=message["id"],
            )
            processed += 1
        return {"processed": processed, "skipped": skipped}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/sources/classroom/sync")
def sync_classroom() -> dict[str, int]:
    """Classify new Classroom items while preserving IDs for deduplication."""
    try:
        items = fetch_recent_classroom_items()
        processed = 0
        skipped = 0
        for item in items:
            if get_item_by_source_id(item["id"]):
                skipped += 1
                continue
            create_item(
                item["text"],
                classify(item["text"]),
                attachments=archive_source_attachments(ARCHIVE_DIRECTORY, item.get("attachments")),
                source="classroom",
                source_id=item["id"],
            )
            processed += 1
        return {"processed": processed, "skipped": skipped}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/sources/whatsapp/demo-load")
def load_whatsapp_demo_data() -> dict[str, int | bool | str]:
    """Classify and persist the representative, non-live WhatsApp demo messages."""
    if has_items_from_source(WHATSAPP_DEMO_SOURCE):
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
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "processed": len(WHATSAPP_DEMO_MESSAGES),
        "already_loaded": False,
        "message": f"Loaded {len(WHATSAPP_DEMO_MESSAGES)} simulated WhatsApp messages.",
    }


@app.post("/queue/{item_id}/done")
def request_queue_item_completion(item_id: int) -> dict:
    """Request human approval before marking one queue item done."""
    item = get_item(item_id)
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
    )


@app.post("/queue/{item_id}/form-draft")
def request_form_draft(item_id: int) -> dict:
    """Stage a copy-only routine-form draft without marking an obligation complete."""
    item = get_item(item_id)
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
    )


@app.get("/pending")
def pending_actions() -> dict[str, list[dict]]:
    """List actions that require a student's decision."""
    return {"actions": get_pending_actions()}


@app.post("/pending/{action_id}/approve")
def approve_action(action_id: int) -> dict:
    """Approve a pending action and apply its underlying local change."""
    try:
        action = approve_pending_action(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not action:
        raise HTTPException(status_code=404, detail="Pending action not found or no longer applicable.")
    return action


@app.post("/pending/{action_id}/reject")
def reject_action(action_id: int) -> dict:
    """Reject a pending action without applying its underlying change."""
    action = reject_pending_action(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Pending action not found.")
    return action


@app.post("/study/upload")
async def upload_study_materials(request: Request) -> dict[str, list[dict]]:
    """Build and persist a topic-ranked plan from two local text files."""
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise HTTPException(status_code=400, detail="Use multipart/form-data with both study files.")

    try:
        form = await request.form()
        question_bank, question_bank_archived_path = await _read_and_archive_text_upload(
            form.get("question_bank"), "question_bank"
        )
        unit_notes, unit_notes_archived_path = await _read_and_archive_text_upload(
            form.get("unit_notes"), "unit_notes"
        )
        topics = build_study_plan(question_bank, unit_notes)
        return {
            "topics": replace_study_plan(
                topics, question_bank_archived_path, unit_notes_archived_path
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/study/plan")
def study_plan() -> dict[str, list[dict]]:
    """Return the persisted, highest-priority-first study topics."""
    return {"topics": get_study_plan()}


@app.get("/archive")
def list_archive() -> dict[str, list[dict]]:
    """List locally retained files that are still available to download."""
    attachments = [
        attachment for attachment in get_archived_attachments()
        if (ARCHIVE_DIRECTORY / attachment["archived_path"]).is_file()
    ]
    return {"attachments": attachments}


@app.get("/archive/{filename}")
def download_archive(filename: str) -> FileResponse:
    """Serve one locally archived attachment without permitting path traversal."""
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid archive filename.")
    archived_file = ARCHIVE_DIRECTORY / filename
    if not archived_file.is_file():
        raise HTTPException(status_code=404, detail="Archived file not found.")
    return FileResponse(
        archived_file,
        filename=original_filename_from_archive(filename),
        media_type="application/octet-stream",
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
        saved_scaffold = create_assignment_help(prompt, scaffold)
        if not saved_scaffold:
            raise RuntimeError("Could not save the assignment scaffold.")
        return saved_scaffold
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/assignment/history")
def assignment_history() -> dict[str, list[dict]]:
    """Return saved assignment scaffolds, newest first."""
    return {"assignments": get_assignment_history()}


def _queue_group(item: dict) -> str:
    """Assign a queue group without guessing when a model deadline is unclear."""
    deadline_date = _parse_deadline(item.get("deadline"))
    if deadline_date is None:
        return "Immediate" if item.get("mandatory") else "Later"

    today = date.today()
    if deadline_date <= today + timedelta(days=1):
        return "Immediate"

    end_of_week = today + timedelta(days=6 - today.weekday())
    return "This Week" if deadline_date <= end_of_week else "Later"


def _parse_deadline(deadline: str | None) -> date | None:
    """Parse common model-returned date formats; leave ambiguous strings unparsed."""
    if not deadline:
        return None

    normalized = deadline.strip()
    for format_string in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(normalized, format_string).date()
        except ValueError:
            pass

    month_day = re.search(r"\b([A-Za-z]+)\s+(\d{1,2})\b", normalized)
    if not month_day:
        return None
    try:
        parsed = datetime.strptime(f"{month_day.group(1)} {month_day.group(2)}", "%B %d").date()
    except ValueError:
        try:
            parsed = datetime.strptime(f"{month_day.group(1)} {month_day.group(2)}", "%b %d").date()
        except ValueError:
            return None

    today = date.today()
    candidate = parsed.replace(year=today.year)
    return candidate if candidate >= today else candidate.replace(year=today.year + 1)


async def _read_and_archive_text_upload(uploaded_file: object, field_name: str) -> tuple[str, str]:
    """Validate, archive, and decode one required UTF-8 .txt upload."""
    if not hasattr(uploaded_file, "filename") or not hasattr(uploaded_file, "read"):
        raise ValueError(f"Upload a .txt file using the '{field_name}' field.")
    if not uploaded_file.filename or Path(uploaded_file.filename).suffix.lower() != ".txt":
        raise ValueError(f"The '{field_name}' file must use the .txt extension.")
    try:
        file_bytes = await uploaded_file.read()
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"The '{field_name}' file must be UTF-8 encoded.") from exc
    archived = archive_attachment(ARCHIVE_DIRECTORY, uploaded_file.filename, file_bytes, "text/plain")
    if not archived:
        raise ValueError(f"The '{field_name}' file is empty or exceeds the 20 MB archive limit.")
    return text, archived["archived_path"]
