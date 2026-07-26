# Triage — Project Overview

## One-line pitch

Triage is a review-first AI student desk that turns scattered college communication into an Action Queue, a ranked Study Plan, and clear human decisions.

## The problem

Students receive important academic information across Gmail, Google Classroom, WhatsApp groups, files, and informal notices. Some messages demand immediate action—registration deadlines, attendance forms, completion polls, lab records, and project checkpoints—while others are useful only for study or are simply noise. The cost is not just inbox overload; it is missed obligations and time spent manually deciding what matters.

Question banks and unit notes create a related problem. Students often have to manually compare material to infer which topics recur and are most worth revising. Assignment prompts can be equally ambiguous, but giving students a finished answer would undermine learning.

## The solution

Triage triages incoming academic information into three structured categories:

- **Obligation**: deadlines, forms, registrations, notices, and polls.
- **Study Material**: question banks, unit notes, and assessment preparation.
- **Noise**: messages that do not need action or study time.

Obligations are grouped into **Immediate**, **This Week**, and **Later**, with explicit deadlines and requirement status. Study material becomes a ranked outline generated from question-bank and unit-note text. Assignment help is deliberately limited to requirements, concepts, approach steps, and test cases.

The key safety mechanism is Human Review. Triage can draft a copy-only response for a completion poll or routine form, but it does not send it, submit a form, or invent a student's personal details. Students may save optional details in their browser—such as their name or roll number—which are deterministically matched only to explicit supported fields in a form draft. Those details never leave the browser. The student can edit and copy the draft themselves; reviewing a form draft does not mark an obligation complete.

## Current implementation

### Ingestion and classification

- Manual text paste plus `.txt`, selectable-text PDF, and DOCX uploads for classification and study planning. Image-only/scanned PDFs are intentionally rejected rather than OCR-guessed.
- Read-only Gmail and Google Classroom sync with persisted last-sync outcomes, clear setup/failure states, and explicit retry controls.
- Clearly marked representative WhatsApp demo data, not a live WhatsApp connection.
- A unified source-labelled stream of recently classified items, refreshed by the open browser every 30 seconds.
- OpenAI structured-output classification with category, reason, deadline, mandatory status, and poll/form detection.
- SQLite/Postgres persistence, source IDs for deduplication, an additive schema-migration ledger, and a private attachment archive: uploaded text files, newly synced Gmail attachments, and accessible Classroom Drive files are retained up to 20 MB each and remain downloadable. Local mode uses disk; hosted mode can use a private S3-compatible bucket. Student-scoped metadata export is available without exposing archive bytes or browser-only profile details.

### Student desk

- Action Queue with urgency grouping, compact cards, detail dialogs, deadline reminders with snooze/optional browser alerts, opt-in hosted Web Push support for explicit today/tomorrow deadlines, and local mark-done requests.
- Archive / History panel with searchable local records, source/category/status filters, and retained-file downloads.
- Approval Drawer with editable poll/form response drafts, browser-local form details, and explicit no-send language.
- Ranked Study Plan with expandable topic outlines.
- Assignment Scaffolding with requirements, concepts, approach, and test cases—never a complete submission.
- Shared demo-password gate, keyboard/arrow navigation, a `Ctrl/Cmd + K` command palette, a pulse-inspired rail, theme selection, and reduced-motion support.

### Deployment

- Frontend: [Vercel](https://triage-27.vercel.app)
- Backend: [Railway](https://triage-production-b91f.up.railway.app/health)
- Hosted Google OAuth now supports per-user, read-only Gmail and Classroom connections when Postgres and the required deployment secrets are configured. Local desktop OAuth remains available for local development.

## Technical architecture

| Concern | Implementation |
| --- | --- |
| Frontend | Vanilla HTML, CSS, and JavaScript |
| Backend | Python, FastAPI, Uvicorn |
| AI workflows | OpenAI Responses API with `gpt-5.6-luna` and JSON schemas |
| Storage | SQLite locally, Postgres for hosted records, and optional private S3-compatible object storage for hosted attachments |
| Google integrations | Gmail API + Google Classroom API using read-only OAuth |
| Hosting | Vercel frontend + Railway backend |

## Why Codex

Codex was the primary engineering collaborator for this solo build. It helped translate the product direction into concrete backend routes, data models, AI schemas, UI behaviors, deployment configuration, debugging, smoke tests, and iterative visual refinements. The product itself uses OpenAI model-backed structured workflows; Codex was also integral to building and validating the surrounding application that makes those workflows safe and usable.

## Important constraints

- No WhatsApp, email, form, or external submission capability exists.
- WhatsApp data in the demo is simulated and labelled as such.
- Hosted Google source sync is read-only and user-scoped. When configured, hosted attachment bytes live in private S3-compatible storage; otherwise the safe local archive fallback remains in use.
- SQLite, local archives, and in-memory sessions make the current deployment a demo environment rather than durable production infrastructure.
- Triage does not generate final academic submissions.

## Next steps

1. Configure provider backups and object-storage lifecycle rules, then add malware scanning, retention controls, and broader file preview support.
2. Add real-time source webhooks where available, broader accessibility testing, and fuller archive-history retention controls. Current source health records the latest user-requested sync and offers an explicit retry; it does not background-retry external providers.
3. Investigate a reliable, policy-compliant WhatsApp integration without compromising the stable demo path.
4. Add more supported routine-form fields only after confirming their privacy and review requirements.

## Demo path

1. Paste a realistic student notice into Stream / Ingest.
2. Show structured classification and the Action Queue.
3. Open the DBMS completion-poll item.
4. Open Human Review and show the editable `Suggested reply: YES, completed` draft.
5. Show ranked Study Plan topics and an Assignment Scaffold.

This demonstrates Triage's core principle: organize attention, draft the next step, and leave the real-world decision with the student.
