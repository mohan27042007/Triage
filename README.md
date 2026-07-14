# Triage
Triage uses Codex to sort scattered WhatsApp, email, and Classroom chaos into a clear Action Queue and a ranked Study Plan — you approve every action, it never decides alone.

## Local-first classification core

This first vertical slice accepts pasted text or a UTF-8 `.txt` file and classifies it with GPT-5.6 as an **Obligation**, **Study Material**, or **Noise** item. It deliberately has no Gmail, Classroom, WhatsApp, OAuth, or automated-action integration yet.

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

### Frontend

In a second terminal, serve the `frontend` folder:

```powershell
cd frontend
py -m http.server 3000
```

Open `http://localhost:3000` in your browser. Paste text or upload a UTF-8 `.txt` file, then select **Classify with Triage**.

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
