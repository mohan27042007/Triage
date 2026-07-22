# Triage

> Sort what college sends into action, study, and calm—without sending or submitting anything for the student.

Triage is a local-first AI student desk for scattered academic communication. It classifies incoming text as an **Obligation**, **Study Material**, or **Noise** item; turns obligations into a deadline-aware Action Queue; builds ranked study outlines from question-bank and unit-note text; and keeps every change behind explicit human review.

**Live demo:** [triage-27.vercel.app](https://triage-27.vercel.app) · **Backend health check:** [Railway API](https://triage-production-b91f.up.railway.app/health)

## What is implemented

- Paste text or upload UTF-8 `.txt` files for classification.
- Structured OpenAI classification with category, evidence-based reason, explicit deadline, mandatory/optional status, and poll/form detection.
- Action Queue grouped into **Immediate**, **This Week**, and **Later**.
- Detail dialogs and a review-first **Mark done** workflow.
- Approval Drawer with editable copy-only drafts for completion polls and routine forms. Optional profile details stay in the student's browser and are matched only to explicit, allow-listed form fields; Triage never invents a value or submits anything externally.
- Study Plan that ranks topics from a question bank and unit notes, with topic outlines rather than generated answers.
- Assignment Scaffolding that returns requirements, concepts, an approach, and test cases—not a submittable solution.
- Local, read-only Gmail and Google Classroom sync after Google OAuth setup.
- Clearly labelled representative WhatsApp demo data; there is no live WhatsApp integration.
- Local archiving and authenticated download of uploaded `.txt` files plus newly synced Gmail attachments and accessible Classroom Drive files (up to 20 MB each).
- Shared demo-password gate, in-memory sessions, in-app deadline reminders with per-item snooze and optional browser notifications, keyboard/pulse-rail navigation, theme controls, and reduced-motion support.

## Product boundaries

Triage is intentionally review-first:

- It does **not** submit forms, send WhatsApp messages, post replies, or make external changes.
- It does **not** invent personal details for form fields.
- Routine form drafts use only details the student explicitly saves in their browser and only for matching supported labels; those details are never sent to the API or classifier.
- It does **not** produce complete academic submissions. Assignment help is planning and self-checking support only.
- Gmail and Classroom access is read-only and is currently supported through the local OAuth workflow.

## Stack

| Layer | Current implementation |
| --- | --- |
| Frontend | Vanilla HTML, CSS, and JavaScript |
| Backend | Python + FastAPI + Uvicorn |
| AI | OpenAI Responses API using `gpt-5.6-luna` structured JSON outputs |
| Local persistence | SQLite |
| Google sources | Gmail API and Google Classroom API via read-only OAuth |
| Hosting | Vercel frontend + Railway FastAPI backend |

## Run locally

### 1. Configure the backend

From the repository root:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set these values in `backend/.env`:

```dotenv
OPENAI_API_KEY=your_openai_api_key
DEMO_PASSWORD=a_shared_demo_password
```

Start the API:

```powershell
uvicorn main:app --reload
```

The API runs at `http://localhost:8000` and exposes interactive documentation at `http://localhost:8000/docs`.

### 2. Serve the frontend

In a second terminal:

```powershell
cd frontend
py -m http.server 3000
```

Open `http://localhost:3000`, then sign in with the shared `DEMO_PASSWORD`.

### 3. Load the local video-demo data (optional)

The seed script is additive and idempotent: it creates five clearly simulated obligation cards, one poll-response draft in Human Review, and one assignment-scaffold example. It does not delete or reset existing data.

```powershell
cd backend
.\.venv\Scripts\python.exe seed_demo_video_data.py
```

## Google source setup (local only)

Create a Google Cloud **Desktop app** OAuth client and save it as `backend/credentials.json`. Then run:

```powershell
cd backend
.\.venv\Scripts\python.exe setup_google_auth.py
```

The browser consent flow writes the local refresh token to `backend/token.json`. Both files are ignored by Git. Return to Triage and use **Sync Gmail** or **Sync Classroom** from Connected Sources.

If the token was created before Classroom or Drive scopes were added, run the setup command again. Triage uses read-only Drive access only to retain attached Classroom files locally; inaccessible files or narrower Workspace grants leave normal Classroom text sync intact.

## API overview

All endpoints except `GET /health` and `POST /auth/login` require the demo bearer token issued by login.

| Endpoint | Purpose |
| --- | --- |
| `POST /auth/login` | Exchanges the shared demo password for an in-memory token. |
| `POST /ingest` | Classifies pasted JSON text or an uploaded UTF-8 `.txt` file. |
| `GET /queue` | Returns open obligations grouped by urgency. |
| `POST /queue/{id}/done` | Creates a pending mark-done review action. |
| `POST /queue/{id}/form-draft` | Creates a copy-only routine-form draft without marking the item done. |
| `GET /pending` | Lists actions awaiting Human Review. |
| `POST /pending/{id}/approve` | Applies an approved local action. |
| `POST /pending/{id}/reject` | Rejects a pending action without changing the item. |
| `POST /sources/gmail/sync` | Imports newly seen Gmail inbox messages after local OAuth. |
| `POST /sources/classroom/sync` | Imports Classroom announcements and coursework after local OAuth. |
| `POST /sources/whatsapp/demo-load` | Loads representative, simulated WhatsApp messages once. |
| `POST /study/upload` | Builds and stores a ranked study plan from two UTF-8 `.txt` files. |
| `GET /study/plan` | Retrieves the latest stored study plan. |
| `POST /assignment/help` | Creates and stores a planning-only assignment scaffold. |
| `GET /assignment/history` | Retrieves saved assignment scaffolds. |
| `GET /archive` | Lists locally retained files that are still available. |
| `GET /archive/{filename}` | Downloads one authenticated locally archived file. |

## Deployment notes

The Vercel/Railway deployment is suitable for a shared demo. Set the Railway variables below:

```text
OPENAI_API_KEY=your_openai_api_key
DEMO_PASSWORD=a_long_shared_demo_password
CORS_ORIGINS=https://triage-27.vercel.app
```

Set Vercel's public `TRIAGE_API_BASE_URL` to the Railway API URL. Never expose `OPENAI_API_KEY` or `DEMO_PASSWORD` in Vercel.

The current hosted backend uses SQLite, a local archive directory, and in-memory sessions. Data and sessions may not survive a redeploy or restart. Google OAuth remains local-only: do not upload `credentials.json` or `token.json` to Railway. Archive copies are local only, bounded to 20 MB per file, and can be downloaded from the Stream archive or an item detail; a production version needs per-user web OAuth, durable storage, and object storage for archives.

Deadline reminders are browser-local: Triage refreshes the open queue every five minutes while the tab is open, shows due-soon items within 24 hours, and can send browser notifications only after the student explicitly enables them. It does not send email, text messages, or background push notifications after the browser is closed.

## How Codex was used

Triage was built through a human-directed, iterative engineering workflow with Codex as the primary coding collaborator. The project owner defined the student problem, interaction boundaries, safety rules, product direction, visual feedback, and deployment choices; Codex helped translate those decisions into the working FastAPI, SQLite, and vanilla-JavaScript application.

Codex was used to scaffold and refine the classification pipeline, review-only Approval Drawer, Google-source ingestion, deployment configuration, navigation behavior, landing flow, demo data, and documentation. It also helped investigate failures such as OAuth scope handling, Gmail classification-schema compatibility, nested panel scrolling, and frontend text rendering. Every external action remains intentionally constrained: the app drafts and stages work, while the student retains the final decision and performs any real submission themselves.

The dated [build log](docs/BUILD_LOG.md) records the implementation phases, commits, validation work, known constraints, and the reported/estimated credit usage. The link is relative, so it opens directly inside this GitHub repository.

## Quick smoke test

Paste this into Stream / Ingest:

```text
Class representative: completion poll — reply YES after you submit your DBMS Lab Record. Please respond by July 22, 2026, 6 PM.
```

Expected result: an **Obligation** with poll/form detection. In the Action Queue, choose **Mark done for review**. Human Review should display an editable draft:

```text
Suggested reply: YES, completed
```

Editing or approving this draft does not send it anywhere.

## Data safety

`backend/triage.db`, `backend/token.json`, `backend/credentials.json`, `backend/.env`, and `backend/archive/` are local user data. They are intentionally excluded from version control. Do not delete, reset, or recreate the database as a testing or cleanup step.

## License

MIT
