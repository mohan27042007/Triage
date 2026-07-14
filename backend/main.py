"""FastAPI server for the local-first Triage classification loop."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from classifier import classify

app = FastAPI(title="Triage API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
            if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
                raise ValueError('JSON requests must use {"text": "..."}.')
            text = payload["text"]
        elif content_type.startswith("multipart/form-data"):
            form = await request.form()
            uploaded_file = form.get("file")
            if uploaded_file is None or not getattr(uploaded_file, "filename", None):
                raise ValueError("Upload a .txt file using the 'file' field.")
            if Path(uploaded_file.filename).suffix.lower() != ".txt":
                raise ValueError("Only .txt files are supported in this local-first slice.")
            try:
                text = (await uploaded_file.read()).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("The uploaded file must be UTF-8 encoded.") from exc
        else:
            raise ValueError("Use application/json or multipart/form-data.")

        return classify(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
