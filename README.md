# Triage

> Sort what college sends into action, study, and calm—without sending or submitting anything for the student.

Triage is a local-first AI student desk for scattered academic communication. It classifies incoming text as an **Obligation**, **Study Material**, or **Noise** item; turns obligations into a deadline-aware Action Queue; builds ranked study outlines from question-bank and unit-note text; and keeps every change behind explicit human review.

**Live demo:** [triage-27.vercel.app](https://triage-27.vercel.app) · **Backend health check:** [Railway API](https://triage-production-b91f.up.railway.app/health)

## What is implemented

- Paste text or upload `.txt`, selectable-text `.pdf`, and `.docx` files for classification. PDFs with no selectable text (such as scanned pages) are rejected rather than silently guessed.
- A unified, source-labelled live stream of recently classified Gmail, Classroom, manual-upload, and WhatsApp-demo items. It refreshes every 30 seconds while the app tab is open; this is local polling, not a webhook feed.
- A dedicated Archive / History panel with local search and source, classification, and open/done filters; retained files remain downloadable from matching records.
- Structured OpenAI classification with category, evidence-based reason, explicit deadline, mandatory/optional status, and poll/form detection.
- Action Queue grouped into **Immediate**, **This Week**, and **Later**.
- Detail dialogs and a review-first **Mark done** workflow.
- Approval Drawer with editable copy-only drafts for completion polls and routine forms. Optional profile details stay in the student's browser and are matched only to explicit, allow-listed form fields; Triage never invents a value or submits anything externally.
- Study Plan that ranks topics from a question bank and unit notes, with topic outlines rather than generated answers.
- Assignment Scaffolding that returns requirements, concepts, an approach, and test cases—not a submittable solution.
- Read-only Gmail and Google Classroom sync with persisted last-sync outcomes, clear setup/failure states, and explicit retry controls after Google OAuth setup.
- Clearly labelled representative WhatsApp demo data; there is no live WhatsApp integration.
- Authenticated archiving and download of uploaded `.txt`, `.pdf`, and `.docx` files plus newly synced Gmail attachments and accessible Classroom Drive files (up to 20 MB each). Local development uses disk; hosted deployments can use private S3-compatible storage.
- Shared demo-password gate, in-memory sessions, in-app deadline reminders with per-item snooze and optional browser notifications, keyboard/pulse-rail navigation, a `Ctrl/Cmd + K` command palette, theme controls, and reduced-motion support.

## Product boundaries

Triage is intentionally review-first:

- It does **not** submit forms, send WhatsApp messages, post replies, or make external changes.
- It does **not** invent personal details for form fields.
- Routine form drafts use only details the student explicitly saves in their browser and only for matching supported labels; those details are never sent to the API or classifier.
- It does **not** produce complete academic submissions. Assignment help is planning and self-checking support only.
- Gmail and Classroom access is read-only and is currently supported through the local OAuth workflow.

## V2 guardrails

Before autonomous source processing is introduced, Triage maintains a synthetic-only
classification regression corpus and explicit quality gates for obligation recall.
See `docs/V2_EVALUATION_GUARDRAILS.md` for the evaluation command, thresholds, secret
handling, retention target, and incident runbook. Real user messages must never be
added to the committed corpus.

## V2 workspace foundation

Hosted accounts now receive one personal workspace and an `individual` membership.
Current owner-scoped behavior remains compatible while `workspace_id` is written for
new hosted records. See `docs/V2_WORKSPACE_FOUNDATION.md` for the additive migration
behavior and staging verification steps.

## V2 PostgreSQL migrations

Hosted PostgreSQL schema changes now use ordered, recorded, advisory-lock-protected
migrations. See `docs/V2_POSTGRES_MIGRATIONS.md` for the staging-first deployment,
verification, and forward-only rollback procedure.

## V2 source connections

Gmail and Classroom now have server-persisted, pause/resume-able connection records
with workspace scope and sync health. See `docs/V2_SOURCE_CONNECTIONS.md`; this does
not enable background syncing yet.

## V2 source deduplication

Imported items now deduplicate by workspace, provider, and provider item ID, so equal
IDs from Gmail and Classroom do not collide. See `docs/V2_SOURCE_DEDUPLICATION.md`
for the data-preserving migration and staging checks.

## V2 durable job queue

Hosted source work now has a durable, leased PostgreSQL job model with idempotency
and bounded retries. It does not schedule or autonomously sync sources yet; see
`docs/V2_DURABLE_JOB_QUEUE.md` for the worker and deployment contract.

## V2 external scheduling

Source schedules now run through a short-lived hosted PostgreSQL cron command that
only enqueues jobs; it never syncs during an API request. See
`docs/V2_EXTERNAL_SCHEDULING.md` for the Railway deployment boundary.

## V2 connector abstraction

Gmail and Classroom manual sync now use a shared normalized connector contract while
remaining read-only and user-requested. See `docs/V2_CONNECTOR_ABSTRACTION.md` for
the explicit cursor boundary and staging verification steps.

## V2 autonomous Google pilot

An opt-in, workspace-allowlisted worker can now read explicitly selected Gmail or
Classroom sources only after the synthetic evaluation gate passes. See
`docs/V2_AUTONOMOUS_GOOGLE_PILOT.md` before configuring any pilot worker.

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

## Google source setup (local desktop mode)

Create a Google Cloud **Desktop app** OAuth client and save it as `backend/credentials.json`. Then run:

```powershell
cd backend
.\.venv\Scripts\python.exe setup_google_auth.py
```

The browser consent flow writes the local refresh token to `backend/token.json`. Both files are ignored by Git. Return to Triage and use **Sync Gmail** or **Sync Classroom** from Connected Sources.

If the token was created before Classroom or Drive scopes were added, run the setup command again. Triage uses read-only Drive access only to retain attached Classroom files locally; inaccessible files or narrower Workspace grants leave normal Classroom text sync intact.

## API overview

All application endpoints require a bearer session token. Local demo mode issues one after the shared-password login; hosted mode issues one after Google OAuth.

| Endpoint | Purpose |
| --- | --- |
| `POST /auth/login` | Exchanges the shared demo password for an in-memory token. |
| `GET /auth/google/start` | Starts hosted Google OAuth when deployment configuration enables it. |
| `GET /auth/google/callback` | Completes hosted OAuth and returns a fragment-only API session token. |
| `POST /ingest` | Classifies pasted JSON text or an uploaded `.txt`, selectable-text `.pdf`, or `.docx` file. |
| `GET /queue` | Returns open obligations grouped by urgency. |
| `GET /stream` | Returns the newest classified items across all available sources. |
| `GET /history` | Searches local item history by text, source, classification, and status. |
| `POST /queue/{id}/done` | Creates a pending mark-done review action. |
| `POST /queue/{id}/form-draft` | Creates a copy-only routine-form draft without marking the item done. |
| `GET /pending` | Lists actions awaiting Human Review. |
| `POST /pending/{id}/approve` | Applies an approved local action. |
| `POST /pending/{id}/reject` | Rejects a pending action without changing the item. |
| `POST /sources/gmail/sync` | Imports newly seen Gmail inbox messages after local OAuth. |
| `POST /sources/classroom/sync` | Imports Classroom announcements and coursework after local OAuth. |
| `GET /sources/status` | Reports the stored connection readiness and latest user-requested Gmail/Classroom sync outcomes; it never starts a sync itself. |
| `POST /sources/whatsapp/demo-load` | Loads representative, simulated WhatsApp messages once. |
| `POST /study/upload` | Builds and stores a ranked study plan from two `.txt`, selectable-text `.pdf`, or `.docx` files. |
| `GET /study/plan` | Retrieves the latest stored study plan. |
| `POST /assignment/help` | Creates and stores a planning-only assignment scaffold. |
| `GET /assignment/history` | Retrieves saved assignment scaffolds. |
| `GET /archive` | Lists locally retained files that are still available. |
| `GET /archive/{filename}` | Downloads one authenticated locally archived file. |
| `GET /account/export` | Downloads the signed-in student's portable metadata export. |
| `GET /push/config` | Returns the signed-in browser's durable-reminder availability and opt-in state. |
| `POST /push/subscribe` | Encrypts an opted-in browser PushSubscription for its owner. |

## Deployment notes

The Vercel/Railway deployment is suitable for a shared demo. Set the Railway variables below:

```text
OPENAI_API_KEY=your_openai_api_key
DEMO_PASSWORD=a_long_shared_demo_password
CORS_ORIGINS=https://triage-27.vercel.app
```

Set Vercel's public `TRIAGE_API_BASE_URL` to the Railway API URL. Never expose `OPENAI_API_KEY` or `DEMO_PASSWORD` in Vercel.

## Hosted Google OAuth

Hosted mode uses Google Web OAuth for a student's own Gmail and Classroom connection. It stores only encrypted Google credential payloads and hashed API session tokens in Railway Postgres. Each stored item, pending action, study plan, assignment scaffold, source deduplication key, and archive listing is scoped to the authenticated student.

Create a Google **Web application** OAuth client, enable Gmail, Classroom, and Drive APIs, and register this exact callback URL in Google Cloud:

```text
https://YOUR-RAILWAY-DOMAIN/auth/google/callback
```

Set these Railway variables without committing their values:

```text
HOSTED_AUTH_ENABLED=true
DATABASE_URL=${{Postgres.DATABASE_URL}}
FRONTEND_ORIGIN=https://YOUR-VERCEL-DOMAIN
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://YOUR-RAILWAY-DOMAIN/auth/google/callback
OAUTH_TOKEN_ENCRYPTION_KEY=...  # Fernet key, generated once and retained
CORS_ORIGINS=https://YOUR-VERCEL-DOMAIN
```

The browser receives the API session token only in the OAuth redirect fragment, then immediately removes it from the URL. Triage uses read-only Google scopes and does not send messages, complete external forms, or submit anything. Local desktop OAuth remains supported when hosted mode is disabled.

### Production hardening

The API returns `no-store`, clickjacking, content-type, referrer, and unused-permission protections on every response. Sensitive endpoints have conservative process-local rate limits; on Railway set `TRUST_PROXY_HEADERS=true` so limits distinguish visitors behind Railway's proxy. The current browser's **Sign out** button now invalidates its hosted session in Postgres (or removes its local demo session). For multiple replicas or public scale, add a shared edge/WAF rate limit and managed monitoring rather than relying only on the in-process limiter.

### Data lifecycle, export, and backups

Triage now records an additive schema-migration ledger (`schema_migrations`) whenever it initializes a database. It never drops tables or deletes student records as part of a migration. A signed-in student can download `GET /account/export` to receive their items, review history, study plan, assignment scaffolds, archive manifest, and applied migration IDs as JSON. Archive file bytes and browser-only routine-form details are deliberately excluded from that export.

The retention policy is conservative: Triage does **not** silently expire or delete records or retained files. Local SQLite and `backend/archive/` remain the student's responsibility to back up; do not copy a live SQLite file while Triage is writing to it. For Railway Postgres, enable the provider's database backup/snapshot capability before relying on hosted data, test restoring into a separate environment, and retain the export file separately. A future hosted object-storage configuration should use lifecycle rules chosen by the student/institution rather than automatic app deletion.

### Durable hosted attachment storage

By default, local development retains files in `backend/archive/`. For a hosted deployment, configure a private S3-compatible bucket (for example Cloudflare R2) in Railway:

```text
ARCHIVE_STORAGE_BACKEND=s3
S3_BUCKET=triage-attachments
S3_ENDPOINT_URL=https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com
S3_REGION=auto
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_PREFIX=triage
```

Do not make the bucket public. Triage hashes each signed-in user's storage namespace and serves downloads only after checking the caller owns the archived-file reference in Postgres. Existing Railway-local files are not migrated automatically; newly retained files use the configured bucket after redeployment.

### Deadline reminders

Triage always keeps the in-app reminder banner and opt-in browser notifications while a tab is open. In hosted mode, it can additionally use private Web Push for a signed-in student who explicitly enables it. Durable reminders are intentionally conservative: the scheduled dispatcher only sends one summary for obligations with an explicit, parseable date that are due **today** or **tomorrow**. The push payload never includes the obligation title or source content; it only asks the student to open Triage.

To enable the optional hosted path, add these Railway variables after deploying this version:

```text
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
VAPID_SUBJECT=mailto:you@example.com
REMINDER_DISPATCH_SECRET=a_long_random_secret
REMINDER_TIMEZONE=Asia/Kolkata
```

Generate the VAPID pair once from the project backend, then keep the printed values private:

```powershell
cd backend
.\.venv\Scripts\python.exe generate_vapid_keys.py
```

Then configure a trusted scheduler to `POST https://YOUR-RAILWAY-DOMAIN/internal/reminders/dispatch` every hour with the header `X-Reminder-Secret` set to that same secret. The dispatch endpoint has no browser-session bypass: it accepts only that secret, and does not send email, SMS, WhatsApp messages, or submit anything externally. Without these variables and scheduler, the existing tab-open reminder behavior remains unchanged.

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

## Keyboard and accessibility

- Press `Ctrl+K` (Windows/Linux) or `Cmd+K` (macOS) after signing in to open the local command palette. Search panel names, common local actions, or recently loaded items; use arrow keys and Enter to select.
- Arrow keys move between dashboard panels when focus is not inside a form control. Escape closes the command palette, detail dialog, approval drawer, or settings drawer.
- The app supports system/light/dark themes and a persistent reduced-motion preference.
- Dialogs keep keyboard focus inside while open, restore it to the trigger when closed, and expose an explicit close control. Touch layouts use larger interactive targets and dynamic viewport sizing.

## Data safety

`backend/triage.db`, `backend/token.json`, `backend/credentials.json`, `backend/.env`, and `backend/archive/` are local user data. They are intentionally excluded from version control. Do not delete, reset, or recreate the database as a testing or cleanup step.

## License

MIT
