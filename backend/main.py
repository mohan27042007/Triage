"""FastAPI server for the local-first Triage classification and Action Queue."""

import re
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .classifier import classify
from .database import create_item, get_open_obligations, initialize_database, mark_done

app = FastAPI(title="Triage API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

initialize_database()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
            if not isinstance(uploaded_file, UploadFile) or not uploaded_file.filename:
                raise ValueError(
                    "Upload a .txt file using the 'file' field."
                )
            if Path(uploaded_file.filename).suffix.lower() != ".txt":
                raise ValueError(
                    "Only .txt files are supported in this local-first slice."
                )
            try:
                text = (await uploaded_file.read()).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("The uploaded file must be UTF-8 encoded.") from exc
        else:
            raise ValueError("Use application/json or multipart/form-data.")

        classification = classify(text)
        return create_item(text, classification)
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


@app.post("/queue/{item_id}/done")
def complete_queue_item(item_id: int) -> dict[str, int | str]:
    """Mark one open obligation as done."""
    if not mark_done(item_id):
        raise HTTPException(status_code=404, detail="Open queue item not found.")
    return {"id": item_id, "status": "done"}


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
