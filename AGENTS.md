# Local data safety

- Treat `backend/triage.db` and every database file as protected user data.
- Never delete, overwrite, reset, recreate, or otherwise modify a database as a side effect of cleanup, testing, or an unrelated task.
- Before any destructive database operation, stop and obtain the user's separate, explicit approval. Create a dated backup first when an existing database is available.
