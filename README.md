# Triage
Triage uses Codex to sort scattered WhatsApp, email, and Classroom chaos into a clear Action Queue and a ranked Study Plan — you approve every action, it never decides alone.

## Local-first classification core

This local-first slice accepts pasted text or a UTF-8 `.txt` file and classifies it with GPT-5.6 Luna as an **Obligation**, **Study Material**, or **Noise** item. Every result is persisted locally in SQLite. Open obligations appear in an Action Queue, where they can be marked done. It deliberately has no Gmail, Classroom, WhatsApp, OAuth, or automated-action integration yet.

## Running locally

### Backend

1. Open a terminal in `backend`.
2. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies and configure your API key:

   ```powershell
   pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

4. Edit `.env` and replace `your_openai_api_key_here` with your OpenAI API key. Never commit this file.
5. Start the API:

   ```powershell
   uvicorn main:app --reload
   ```

The API will run at `http://localhost:8000`; visit `http://localhost:8000/docs` for the interactive endpoint documentation.

### API endpoints

- `POST /ingest` — accepts JSON (`{"text":"..."}`) or a multipart UTF-8 `.txt` upload (`file`); classifies and stores the item.
- `GET /queue` — returns open obligations grouped as `Immediate`, `This Week`, and `Later`.
- `POST /queue/{id}/done` — creates a pending request to mark an open obligation done; it does not change the item yet.
- `GET /pending` — lists human-review actions awaiting a decision.
- `POST /pending/{id}/approve` — applies an approved pending action (currently `mark_done`).
- `POST /pending/{id}/reject` — rejects a pending action without applying it.
- `POST /study/upload` — accepts UTF-8 `.txt` files named `question_bank` and `unit_notes`, then builds and persists a ranked study plan.
- `GET /study/plan` — returns the latest persisted study topic list, ordered by weight.
- `GET /health` — confirms the API is running.

### Frontend

In a second terminal, serve the `frontend` folder:

```powershell
cd frontend
py -m http.server 3000
```

Open `http://localhost:3000` in your browser. Paste text or upload a UTF-8 `.txt` file, then select **Classify with Triage**.

### Queue smoke test

1. Start the backend and frontend as above.
2. Submit the obligation example below. It should appear in **Immediate** or **This Week**, depending on the current date and extracted deadline.
3. Select **Mark done**. The item should remain in the queue and appear under **Human Review**.
4. Approve it. The item should then disappear from the queue; rejecting it leaves the item open.
5. Submit the study-material example. It should classify correctly but should not appear in the Action Queue.

### Study Plan smoke test

1. Create a small `question_bank.txt` with several questions that repeat a few topics, plus matching `unit_notes.txt`.
2. In the Study Plan section, upload both files and select **Build study plan**.
3. Confirm the result shows ranked topics, a 1–10 weight, and an expandable outline for each topic.
4. Restart the API and refresh the page; the latest study plan should still appear.

### Manual smoke-test messages

**Obligation**

```text
All students must complete the Build Week registration form by Friday, July 17 at 5 PM. Attendance will be verified.
```

**Study Material**

```text
Unit 3 question bank: Explain the difference between supervised and unsupervised learning. Compare both approaches with one example each.
```

## License

MIT
