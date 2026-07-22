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

- Manual text paste and UTF-8 `.txt` uploads.
- Read-only Gmail and Google Classroom sync in the local OAuth setup.
- Clearly marked representative WhatsApp demo data, not a live WhatsApp connection.
- OpenAI structured-output classification with category, reason, deadline, mandatory status, and poll/form detection.
- SQLite persistence, source IDs for deduplication, and local archive downloads for uploaded text files.

### Student desk

- Action Queue with urgency grouping, compact cards, detail dialogs, deadline reminders, and local mark-done requests.
- Approval Drawer with editable poll/form response drafts, browser-local form details, and explicit no-send language.
- Ranked Study Plan with expandable topic outlines.
- Assignment Scaffolding with requirements, concepts, approach, and test cases—never a complete submission.
- Shared demo-password gate, keyboard/arrow navigation, a pulse-inspired rail, theme selection, and reduced-motion support.

### Deployment

- Frontend: [Vercel](https://triage-27.vercel.app)
- Backend: [Railway](https://triage-production-b91f.up.railway.app/health)
- Local mode remains the supported place for Google OAuth source connections.

## Technical architecture

| Concern | Implementation |
| --- | --- |
| Frontend | Vanilla HTML, CSS, and JavaScript |
| Backend | Python, FastAPI, Uvicorn |
| AI workflows | OpenAI Responses API with `gpt-5.6-luna` and JSON schemas |
| Storage | SQLite for the local/demo workflow |
| Google integrations | Gmail API + Google Classroom API using read-only OAuth |
| Hosting | Vercel frontend + Railway backend |

## Why Codex

Codex was the primary engineering collaborator for this solo build. It helped translate the product direction into concrete backend routes, data models, AI schemas, UI behaviors, deployment configuration, debugging, smoke tests, and iterative visual refinements. The product itself uses OpenAI model-backed structured workflows; Codex was also integral to building and validating the surrounding application that makes those workflows safe and usable.

## Important constraints

- No WhatsApp, email, form, or external submission capability exists.
- WhatsApp data in the demo is simulated and labelled as such.
- Google source sync is read-only and presently designed for local OAuth, not hosted per-user accounts.
- SQLite, local archives, and in-memory sessions make the current deployment a demo environment rather than durable production infrastructure.
- Triage does not generate final academic submissions.

## Next steps

1. Add per-user hosted Google OAuth and durable account/session storage.
2. Move from SQLite/local archives to managed storage and object storage.
3. Add robust connection health, retry states, source search, and archive/history views.
4. Extend attachment handling beyond UTF-8 text uploads.
5. Investigate a reliable, policy-compliant WhatsApp integration without compromising the stable demo path.
6. Add more supported routine-form fields only after confirming their privacy and review requirements.

## Demo path

1. Paste a realistic student notice into Stream / Ingest.
2. Show structured classification and the Action Queue.
3. Open the DBMS completion-poll item.
4. Open Human Review and show the editable `Suggested reply: YES, completed` draft.
5. Show ranked Study Plan topics and an Assignment Scaffold.

This demonstrates Triage's core principle: organize attention, draft the next step, and leave the real-world decision with the student.
