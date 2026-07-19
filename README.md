# Agentic Monitor (scaffold)

Minimal scaffold for the Agentic AI Edge Device & Website Monitoring System.

Quickstart

1. Create a virtualenv and activate it:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill secrets.

3. Run the app:

```bash
uvicorn main:app --reload --port 8000
```

## Features
- Monitor device and website metrics and persist as `Event` records in SQLite
- Classify events using a local SLM (Ollama) into `normal|warning|critical`
- Persistent RAG store (ChromaDB) with embeddings from `sentence-transformers` for runbook context
- LLM alert generation via Anthropic or OpenAI
- Escalation orchestration with email notifications and alert storm protection

## Testing
Run unit tests (lightweight tests will skip heavy deps when missing):

```bash
python -m unittest discover -v tests
```

Integration tests in `tests/test_integration.py` will be skipped if `SQLAlchemy` or other optional packages are not installed. To run full integration tests, install requirements and set the env vars described below.

## Environment variables
Create a `.env` file or export these environment variables:

- `LLM_PROVIDER` — `anthropic` (default) or `openai`
- `ANTHROPIC_API_KEY` — your Anthropic API key (if using Anthropic)
- `OPENAI_API_KEY` — your OpenAI API key (if using OpenAI)
- `OLLAMA_BASE_URL` — URL for local Ollama (default `http://localhost:11434`)
- `OLLAMA_MODEL` — model name for Ollama (default `phi3`)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` — SMTP settings for email
- `ALERT_EMAIL_TO` — default recipient for alerts
- `DATABASE_URL` — SQLAlchemy database URL (default `sqlite:///./monitor.db`)
- `CHROMA_PERSIST_DIR` — directory for ChromaDB persistence (default `./chroma_store`)

If you want, I can add a `docker-compose` that runs Ollama and necessary services for a full local integration environment.
