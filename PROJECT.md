Commit prepared documentation for the local-first Triage classification core.

---

# Triage - Local-First Classification Core

## Project Overview

Triage is a student inbox assistant built as a local-first prototype to classify WhatsApp, email, and other text communications into three categories:

- **Obligation**: Tasks requiring student action (deadlines, registration, forms)
- **Study Material**: Academic content for learning/assessment (notes, questions)
- **Noise**: Irrelevant content, casual chat, promotional messages

## Technical Architecture

### Backend (Python 3.13)
- **Framework**: FastAPI 0.115.0
- **Server**: Uvicorn with hot reload
- **API Key**: OpenAI API integration via python-dotenv
- **Classifier**: GPT-5.6 with JSON schema validation
- **Endpoints**:
  - `GET /health` - Health check
  - `POST /ingest` - Text ingestion and classification
    - JSON body: `{"text": "message text"}`
    - Form upload: UTF-8 `.txt` file via `file` field

### Frontend (Vanilla JavaScript)
- **Framework**: Plain HTML + CSS + JS (no React yet)
- **Server**: Python HTTP server (port 3000)
- **Features**:
  - Text paste area
  - File upload (.txt only, UTF-8 encoded)
  - Real-time classification
  - Categorized results with badges and details

### Classifier Integration
- **Model**: GPT-5.6
- **Format**: Structured JSON response with:
  - `category`: One of {"Obligation", "Study Material", "Noise"}
  - `reason`: Evidence-based classification explanation
  - `deadline`: Optional explicit deadline string
  - `mandatory`: Boolean/nulp for required/optional

## Setup & Run

### Prerequisites
- Python 3.13+
- pip (available via py launcher on Windows)

### Backend Setup

1. Open terminal in project root:
   ```cmd
   cd backend
   ```

2. Create virtual environment:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies and create .env:
   ```powershell
   pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

4. Configure API key in `backend/.env`:
   ```dotenv
   OPENAI_API_KEY=your_actual_openai_api_key_here
   ```

5. Start the FastAPI server:
   ```powershell
   uvicorn main:app --reload
   ```

   Server will be available at `http://localhost:8000`

### Frontend Setup

6. Open new terminal:
   ```cmd
   cd frontend
   ```

7. Start static server:
   ```powershell
   py -m http.server 3000
   ```

   Frontend available at `http://localhost:3000`

### Testing

Test with provided samples:

**Obligation Sample**:
```text
All students must complete the Build Week registration form by Friday, July 17 at 5 PM. Attendance will be verified.
```

**Study Material Sample**:
```text
Unit 3 question bank: Explain the difference between supervised and unsupervised learning. Compare both approaches with one example each.
```

## Architecture Notes

- **Local-first**: All text input processed locally, no external accounts or OAuth
- **No external integrations**: Deliberately excludes Gmail, ClassRoom, WhatsApp, Pulse Rail components
- **Functional-only slice**: Focuses on core classification loop proof-of-concept
- **Minimal styling**: Plain design to validate classification logic
- **Schema validation**: Strict JSON validation for consistent responses

## File Structure

```
Triage/
├── backend/
│   ├── main.py           # FastAPI API server
│   ├── classifier.py     # Classification logic
│   ├── requirements.txt  # Python dependencies
│   ├── .env.example      # API key template
│   └── .env             # OpenAI API key (gitignored)
├── frontend/
│   ├── index.html       # Main UI
│   ├── styles.css       # Styling
│   └── app.js           # Client logic
├── README.md            # Project documentation
└── .gitignore          # Ignore patterns
```

## Documentation Links

- **Interactive API docs**: http://localhost:8000/docs
- **Health check**: http://localhost:8000/health

## Code Quality

- **Type checking**: mypy with strict mode enabled
- **Formatting**: Black (PEP-8 compliant)
- **Linting**: flake8 (79-char line limit)
- **Syntax validation**: Python compile checks
- **Error handling**: Structured HTTPException responses

## Deployment Considerations

- **Environment**: Intended for local development and testing
- **Security**: API key stored in .env (never committed)
- **CORS**: Configured for localhost origins only
- **Input validation**: Strict type and format checks
- **Error reporting**: Clear user-friendly error messages

## Future Work

- Gmail integration for reading emails
- ClassRoom WhatsApp notifications
- Pulse Rail design system implementation
- User approval workflow for actions
- Automated action execution
- Advanced classification features
- Dashboard and analytics

## Testing Strategy

1. **Manual smoke tests**: Core classification features
2. **End-to-end validation**: Real user scenarios
3. **API validation**: Type and schema checks
4. **Error handling**: Invalid input scenarios
5. **Performance testing**: Large file uploads
6. **Integration testing**: Backend-frontend communication

## Testing the Implementation

Once the server is running, test end-to-end with:

1. **Obligation message**:
   - Submit: "All students must complete the Build Week registration form by Friday, July 17 at 5 PM. Attendance will be verified."
   - Expected result: Category: "Obligation", with deadline field populated

2. **Study Material sample**:
   - Submit: "Unit 3 question bank: Explain the difference between supervised and unsupervised learning. Compare both approaches with one example each."
   - Expected result: Category: "Study Material", with detailed reason

3. **Noise test**:
   - Submit: "Hello everyone! Hope you're having a great day. Just wanted to say hi!"
   - Expected result: Category: "Noise" (no deadline or mandatory fields)

The system should correctly classify all three message types with appropriate details.
