# LongDoc Translator Agent

LongDoc Translator Agent is a local-first MVP for structured long-document translation. The first target workflow is paper translation:

```text
upload document -> parse -> chunk -> extract terms -> human term review -> translate chunks -> checkpoint -> export Markdown
```

The project focuses on the engineering depth around long documents: structured parsing, terminology consistency, human-in-the-loop review, sliding context memory, checkpoint recovery, risk reporting, and bilingual output.

## MVP Scope

Included:

- Upload `PDF / Markdown / TXT`
- Parse PDF with Docling and normalize Markdown/TXT into the same pipeline
- Split by section, paragraph, and structural blocks
- Extract terminology through an OpenAI-compatible LLM API
- Confirm terms before translation continues
- Translate by chunk with checkpoint persistence
- Resume failed jobs from completed chunks
- Cancel jobs at chunk boundaries
- Export `bilingual.md`, `translated.md`, and `report.md`
- Web console for upload, review, progress, and downloads

Deferred:

- Login, multi-user isolation, payment, cloud storage
- Multi-job concurrency
- WebSocket/SSE push
- Vector DB/RAG/translation memory
- DOCX/HTML/PDF export
- Full novel mode

## Tech Stack

- Backend: Python, FastAPI, SQLAlchemy, SQLite, Pydantic
- Agent workflow: LangGraph-oriented service boundaries
- Parser: Docling for PDF, native Markdown/TXT parsing for quick demos
- LLM: DeepSeek through an OpenAI-compatible API
- Frontend: React, Vite, TypeScript
- Runtime storage: local filesystem under `storage/`

## Environment

Copy `.env.example` to `.env` and fill in your DeepSeek key:

```powershell
Copy-Item .env.example .env
```

Key LLM settings:

```text
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=your_deepseek_key
LLM_MODEL=deepseek-v4-flash
```

Secrets must stay in `.env`; do not commit API keys.

Prepare Docling before the first PDF run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\docling-tools.exe models download layout tableformerv2
```

Docling stores models in the user cache. The first download requires access to Hugging Face; an unavailable model is reported as parser error `50002`. OCR defaults to `rapidocr-onnxruntime` to avoid backend selection changing when PyTorch is installed.

## Backend Smoke

```powershell
cd backend
$env:PYTHONPATH=(Get-Location).Path
python -m pytest
```

Run the backend during development:

```powershell
cd backend
$env:PYTHONPATH=(Get-Location).Path
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```text
GET http://127.0.0.1:8000/api/health
```

## Frontend Build

Node.js 20+ is required.

```powershell
cd frontend
npm install
npm run build
```

Run the frontend during development:

```powershell
cd frontend
npm run dev
```

## Project Layout

```text
backend/
  app/
    api/
    core/
    db/
    models/
    schemas/
    services/
    storage/
    main.py
  tests/
frontend/
  src/
docs/
samples/
storage/
```

`storage/` is a runtime directory. Keep uploaded files, parsed output, SQLite databases, and generated reports out of Git.
