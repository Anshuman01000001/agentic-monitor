# Agentic AI Edge Device & Website Monitoring System
## Project Handoff Document — Plan then Code

---

## Project Overview

Build an agentic AI monitoring system that watches two classes of targets in real time:

1. **The local machine** (the developer's own computer acting as an edge device) — CPU, memory, disk, network, and running processes
2. **Websites** — a user-defined list of domains that are checked for uptime, response time, HTTP status, and SSL certificate validity

The system uses a **Small Language Model (SLM) running locally via Ollama** for fast, lightweight anomaly classification on every event. It uses a **cloud LLM API** (e.g. Claude or OpenAI) only for high-confidence escalation decisions and natural language alert generation, keeping costs low.

When a genuine anomaly is detected, the system sends a **formatted email alert** with full context. All events — normal and anomalous — are logged and queryable. A **RAG pipeline** gives the agent access to a runbook of known issues and resolutions, which it retrieves before making escalation decisions. A **web dashboard** displays real-time system status, recent events, and alert history.

The design philosophy is **human-in-the-loop** — the agent classifies and recommends, but the operator retains full visibility and override capability at all times. Alert fatigue is avoided through **conditional escalation** — only genuine anomalies that cross a confidence threshold trigger email notifications.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   DATA COLLECTION                    │
│  ┌─────────────────┐    ┌──────────────────────┐    │
│  │  Device Monitor  │    │   Website Monitor     │    │
│  │  (psutil)        │    │   (httpx / ssl)       │    │
│  └────────┬────────┘    └──────────┬───────────┘    │
└───────────┼──────────────────────── ┼───────────────┘
            │                         │
            ▼                         ▼
┌─────────────────────────────────────────────────────┐
│                 TELEMETRY PIPELINE                   │
│         Collects, normalises, and queues events      │
│                    (SQLite)                          │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│              SLM CLASSIFICATION LAYER                │
│         Ollama (Phi-3 or Mistral) running locally    │
│   Classifies each event: normal / warning / critical │
└─────────────────────────┬───────────────────────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
         normal/warning           critical
              │                       │
              ▼                       ▼
        Log to DB            ┌────────────────┐
                             │  RAG PIPELINE  │
                             │  Retrieve from │
                             │  runbook store │
                             │  (ChromaDB)    │
                             └───────┬────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │   LLM API LAYER       │
                          │  (Claude / OpenAI)    │
                          │  Generate human-      │
                          │  readable alert with  │
                          │  runbook context      │
                          └──────────┬───────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │   EMAIL NOTIFICATION  │
                          │   (SMTP / SendGrid)   │
                          └──────────────────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │      DASHBOARD        │
                          │   (FastAPI + React    │
                          │    or Jinja2)         │
                          └──────────────────────┘
```

---

## Tech Stack

### Backend
| Component | Technology | Reason |
|---|---|---|
| Language | Python 3.11+ | Ecosystem for AI/monitoring tooling |
| Web framework | FastAPI | Async support, you have prior experience |
| Task scheduling | APScheduler | Run monitoring checks on intervals |
| Device telemetry | psutil | Cross-platform CPU, memory, disk, network |
| Website monitoring | httpx | Async HTTP requests with timeout handling |
| SSL checking | Python ssl + certifi | Certificate expiry detection |
| Database | SQLite (via SQLAlchemy) | Lightweight, no setup, persistent event log |
| SLM runtime | Ollama | Run Phi-3 or Mistral locally, no API cost |
| SLM model | Phi-3 Mini or Mistral 7B | Fast classification, runs on consumer hardware |
| LLM API | Anthropic Claude API or OpenAI | High-quality alert generation, used sparingly |
| RAG vector store | ChromaDB | Lightweight, local, no external service needed |
| Embeddings | sentence-transformers | Local embedding generation for RAG |
| Email | SMTP (Gmail) or SendGrid API | Email alert delivery |
| Environment config | python-dotenv | API keys and config management |

### Frontend (Dashboard)
| Component | Technology | Reason |
|---|---|---|
| Option A (simpler) | FastAPI + Jinja2 templates | Single codebase, no build step |
| Option B (richer) | React + Vite served by FastAPI | Better real-time UI, more interactive |
| Charts | Chart.js or Recharts | CPU/memory/response time graphs |
| Real-time updates | WebSockets or SSE | Push new events to dashboard without polling |
| Styling | Tailwind CSS | Fast, clean UI |

**Recommendation:** Start with Option A (Jinja2) to ship faster. Upgrade to Option B once core functionality is working.

---

## File Structure

```
agentic-monitor/
│
├── main.py                        # Entry point — starts FastAPI app and scheduler
├── .env                           # API keys, email config, target domains (never commit)
├── .env.example                   # Template showing required env vars
├── requirements.txt               # All dependencies
├── README.md                      # Setup instructions
│
├── config/
│   └── settings.py                # Loads .env, defines constants, thresholds
│
├── monitors/
│   ├── __init__.py
│   ├── device_monitor.py          # Collects CPU, memory, disk, network via psutil
│   └── website_monitor.py         # Checks HTTP status, response time, SSL expiry
│
├── pipeline/
│   ├── __init__.py
│   ├── collector.py               # Normalises raw monitor output into event schema
│   └── scheduler.py               # APScheduler jobs — runs monitors on intervals
│
├── agent/
│   ├── __init__.py
│   ├── classifier.py              # SLM classification via Ollama — normal/warning/critical
│   ├── rag.py                     # RAG pipeline — embeds runbook, retrieves context
│   ├── escalator.py               # Decides whether to escalate based on SLM output
│   └── alert_generator.py         # Calls LLM API to generate human-readable alert text
│
├── notifications/
│   ├── __init__.py
│   └── email_notifier.py          # Formats and sends email alerts via SMTP or SendGrid
│
├── database/
│   ├── __init__.py
│   ├── models.py                  # SQLAlchemy models — Event, Alert, Target
│   └── db.py                      # DB connection, session management, query helpers
│
├── runbooks/
│   ├── high_cpu.md                # Runbook: high CPU usage
│   ├── memory_pressure.md         # Runbook: memory exhaustion
│   ├── disk_full.md               # Runbook: disk space critical
│   ├── website_down.md            # Runbook: website unreachable
│   ├── ssl_expiry.md              # Runbook: SSL certificate expiring
│   └── high_response_time.md      # Runbook: website slow response
│
├── dashboard/
│   ├── routes.py                  # FastAPI router for dashboard endpoints
│   ├── templates/                 # Jinja2 HTML templates (if Option A)
│   │   ├── base.html
│   │   ├── index.html             # Main dashboard view
│   │   └── alerts.html            # Alert history view
│   └── static/                    # CSS, JS, Chart.js
│       ├── style.css
│       └── dashboard.js
│
└── tests/
    ├── test_device_monitor.py
    ├── test_website_monitor.py
    ├── test_classifier.py
    └── test_rag.py
```

---

## Data Models

### Event (every telemetry reading)
```python
class Event:
    id: int
    timestamp: datetime
    source_type: str        # "device" or "website"
    source_name: str        # hostname or domain
    metric_name: str        # "cpu_percent", "response_time_ms", "ssl_days_remaining"
    metric_value: float
    classification: str     # "normal", "warning", "critical" — set by SLM
    confidence: float       # SLM confidence score 0.0–1.0
    escalated: bool         # whether an alert was sent
    raw_data: dict          # full snapshot as JSON
```

### Alert (every email sent)
```python
class Alert:
    id: int
    timestamp: datetime
    event_id: int           # FK to Event
    alert_text: str         # LLM-generated human-readable alert
    runbook_context: str    # RAG-retrieved runbook excerpt used
    email_sent_to: str
    email_sent_at: datetime
```

### Target (user-defined monitoring targets)
```python
class Target:
    id: int
    target_type: str        # "device" or "website"
    name: str               # hostname or domain (e.g. "github.com")
    enabled: bool
    check_interval_seconds: int
    added_at: datetime
```

---

## Feature Specifications

### Feature 1: Device Monitor

**What it does:** Collects real-time telemetry from the local machine on a configurable interval (default every 60 seconds).

**Metrics to collect:**
- CPU usage percent (overall and per-core)
- Memory usage percent and available MB
- Disk usage percent per mounted partition
- Network bytes sent/received per interval (delta, not cumulative)
- List of top 5 processes by CPU usage

**Implementation notes:**
- Use `psutil` for all metrics
- Each metric becomes a separate Event record so they can be classified individually
- Network metric should calculate delta since last reading, not raw cumulative bytes
- Process list should be captured as JSON in `raw_data`

**Thresholds (configurable in settings.py):**
- CPU > 85% = warning candidate
- CPU > 95% = critical candidate
- Memory > 85% = warning candidate
- Disk > 90% = critical candidate
- These are passed to the SLM as context, not used as hard cutoffs

---

### Feature 2: Website Monitor

**What it does:** Checks a user-defined list of domains on a configurable interval (default every 5 minutes).

**Checks per domain:**
- HTTP status code (200 = healthy, anything else = anomaly)
- Response time in milliseconds
- Whether the site is reachable at all (timeout = critical)
- SSL certificate days remaining (warning at <30 days, critical at <7 days)
- Redirect chain (flag if unexpected redirects occur)

**Implementation notes:**
- Use `httpx` with async requests and a 10-second timeout
- Check both `http://` and `https://` — flag if HTTP doesn't redirect to HTTPS
- SSL check should parse the cert expiry date and calculate days remaining
- Domains are loaded from `.env` as a comma-separated list: `MONITOR_DOMAINS=github.com,google.com`
- Each check produces one Event per metric per domain

---

### Feature 3: SLM Classification Layer

**What it does:** Every Event passes through the SLM before anything else happens. The SLM classifies it as `normal`, `warning`, or `critical` and returns a confidence score.

**How it works:**
- Use Ollama to run Phi-3 Mini or Mistral 7B locally
- Send the event data as a structured prompt to the SLM
- Parse the response to extract classification and confidence
- Write classification back to the Event record

**Prompt structure:**
```
You are a system monitoring agent. Classify the following telemetry event.

Event:
- Source: {source_type} ({source_name})
- Metric: {metric_name}
- Value: {metric_value}
- Context: {additional_context}

Known thresholds:
{threshold_context}

Respond in JSON only:
{"classification": "normal|warning|critical", "confidence": 0.0-1.0, "reason": "one sentence"}
```

**Implementation notes:**
- Only events classified as `critical` with confidence > 0.75 proceed to escalation
- `warning` events are logged but do not trigger alerts unless they persist across 3 consecutive readings
- Parse SLM JSON response defensively — handle malformed output gracefully
- Log the SLM reason string to the Event record for dashboard display

---

### Feature 4: RAG Pipeline

**What it does:** When an event is escalated, the RAG pipeline retrieves the most relevant runbook entry before the LLM generates the alert. This gives the LLM grounded, specific context rather than generating from scratch.

**How it works:**
1. On startup, embed all markdown files in `/runbooks/` using `sentence-transformers`
2. Store embeddings in ChromaDB (local persistent store)
3. When escalating an event, embed the event description and query ChromaDB for the top 2 most similar runbook chunks
4. Pass retrieved chunks to the LLM as context in the alert generation prompt

**Runbook files to create (one per known issue type):**
- `high_cpu.md` — causes, triage steps, escalation criteria
- `memory_pressure.md` — causes, triage steps
- `disk_full.md` — causes, immediate actions, escalation
- `website_down.md` — triage steps, common causes
- `ssl_expiry.md` — renewal process, urgency levels
- `high_response_time.md` — triage steps, common causes

**Implementation notes:**
- Use `chromadb` with a local persistent directory `./chroma_store/`
- Use `sentence-transformers` model `all-MiniLM-L6-v2` for embeddings — lightweight and accurate
- Chunk runbook files by section (split on `##` headers) so retrieval is granular
- Re-embed runbooks on startup if files have changed (check file modified timestamps)

---

### Feature 5: LLM API Alert Generation

**What it does:** Uses the cloud LLM API to generate a clear, human-readable alert message combining the event data and the retrieved runbook context.

**When it's called:** Only after SLM classifies an event as critical AND RAG has retrieved context. This keeps API costs low.

**Prompt structure:**
```
You are an IT operations monitoring agent. Generate a concise alert notification.

Event details:
{event_data}

Relevant runbook context:
{rag_context}

Generate an alert with:
1. One sentence summary of what is wrong
2. The metric value and why it's concerning
3. Immediate recommended action from the runbook
4. Severity level

Keep the total response under 150 words. Write for an IT operations analyst.
```

**Implementation notes:**
- Use the Anthropic Python SDK or OpenAI SDK — make this configurable via `.env`
- `LLM_PROVIDER=anthropic` or `LLM_PROVIDER=openai`
- Store the generated alert text in the Alert record
- Cap LLM calls — if the same source generates more than 3 alerts in 10 minutes, suppress further alerts and send one "alert storm" notification instead

---

### Feature 6: Email Notifications

**What it does:** Sends a formatted HTML email when an alert is generated.

**Email contents:**
- Subject: `[CRITICAL] {source_name} — {metric_name} alert`
- Body: LLM-generated alert text
- Metric value and timestamp
- Runbook excerpt used
- Link to dashboard (if deployed)
- Footer: "This alert was generated by Agentic Monitor. Reply to acknowledge."

**Implementation notes:**
- Primary: SMTP via Gmail (use App Password, not account password)
- Config in `.env`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_TO`
- Use Python `smtplib` + `email.mime` for HTML formatting
- Log every email sent to the Alert table including timestamp and recipient
- On SMTP failure, log the error and retry once after 30 seconds

---

### Feature 7: Dashboard

**What it does:** A web interface showing real-time system status, recent events, and alert history.

**Pages:**

**1. Main Dashboard (`/`)**
- Status cards at the top: one per monitored target (green/amber/red based on last classification)
- Live CPU and memory graph for the device (last 30 minutes, updates every 30 seconds)
- Website response time graph per domain (last 24 hours)
- Recent events table: last 50 events with source, metric, value, classification, timestamp
- Active alerts banner if any critical events in last 15 minutes

**2. Alert History (`/alerts`)**
- Full table of all sent alerts
- Columns: timestamp, source, metric, value, alert text, runbook used
- Filter by source, severity, date range

**3. Targets (`/targets`)**
- List of all monitored targets
- Toggle enable/disable per target
- Add new website domain via form
- Shows last check time and status per target

**Real-time updates:**
- Use Server-Sent Events (SSE) to push new events to the dashboard without full page reload
- FastAPI has native SSE support via `StreamingResponse`

**Implementation notes:**
- Use Jinja2 templates for server-side rendering
- Chart.js for graphs — load data via `/api/metrics/{source}` JSON endpoint
- Tailwind CSS via CDN for styling
- Dashboard should work without JavaScript for the static tables — JS only enhances the graphs and live updates

---

## Environment Variables (.env.example)

```
# LLM Configuration
LLM_PROVIDER=anthropic                    # "anthropic" or "openai"
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here              # only needed if using openai

# Ollama SLM Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=phi3                         # or "mistral"

# Email Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
ALERT_EMAIL_TO=recipient@gmail.com

# Monitoring Targets
MONITOR_DOMAINS=github.com,google.com,example.com

# Monitoring Intervals (seconds)
DEVICE_CHECK_INTERVAL=60
WEBSITE_CHECK_INTERVAL=300

# Escalation Thresholds
SLM_CRITICAL_CONFIDENCE_THRESHOLD=0.75
CONSECUTIVE_WARNINGS_BEFORE_ALERT=3
ALERT_STORM_WINDOW_MINUTES=10
ALERT_STORM_MAX_ALERTS=3

# Database
DATABASE_URL=sqlite:///./monitor.db

# ChromaDB
CHROMA_PERSIST_DIR=./chroma_store
```

---

## Agentic Patterns Used

| Pattern | Where it appears |
|---|---|
| ReAct (Reasoning + Acting) | SLM classifies → RAG retrieves → LLM generates → email sent |
| RAG | Runbook retrieval before alert generation |
| Human-in-the-loop | Dashboard gives operator full visibility and override |
| Conditional escalation | Only critical + high confidence events trigger alerts |
| Tool use | Agent has tools: check_device, check_website, send_email, query_runbook |
| Multi-step reasoning | SLM classification → confidence check → RAG → LLM → notification |
| Memory (external) | SQLite event log persists all history |
| Alert storm prevention | Cap on alerts per source per time window |

---

## Build Order for the Implementing LLM

Build in this exact sequence. Do not skip ahead — each step depends on the previous.

1. **Project scaffold** — create file structure, `requirements.txt`, `.env.example`, `settings.py`
2. **Database layer** — `models.py`, `db.py`, SQLAlchemy setup, create tables on startup
3. **Device monitor** — `device_monitor.py` using psutil, test that it returns correct metrics
4. **Website monitor** — `website_monitor.py` using httpx, SSL check, test against real domains
5. **Collector and scheduler** — `collector.py` normalises output into Event schema, `scheduler.py` runs monitors on interval
6. **SLM classifier** — `classifier.py` sends events to Ollama, parses JSON response, writes classification to DB
7. **Runbook files** — write all 6 runbook markdown files with real triage content
8. **RAG pipeline** — `rag.py` embeds runbooks into ChromaDB on startup, retrieves context for escalated events
9. **LLM alert generator** — `alert_generator.py` calls cloud LLM API with event + RAG context, returns alert text
10. **Email notifier** — `email_notifier.py` sends HTML email, logs to Alert table
11. **Escalator** — `escalator.py` orchestrates steps 6–10, enforces confidence threshold and alert storm cap
12. **Dashboard routes and templates** — `routes.py`, `index.html`, `alerts.html`, `targets.html`
13. **Real-time SSE** — push new events to dashboard
14. **API endpoints** — `/api/metrics/{source}` for Chart.js data
15. **Main entry point** — `main.py` wires everything together, starts FastAPI and scheduler
16. **Tests** — write tests for monitors, classifier, and RAG pipeline

---

## Constraints and Notes for the Implementing LLM

- All SLM inference must go through Ollama at `localhost:11434` — do not call external APIs for classification
- The cloud LLM API is called only in `alert_generator.py` — nowhere else
- ChromaDB must use a local persistent directory — do not use the in-memory client
- SQLite database file must be created automatically on first run — no manual migration step
- All secrets must come from `.env` via `python-dotenv` — no hardcoded credentials anywhere
- The dashboard must be accessible at `http://localhost:8000` with no authentication for local development
- APScheduler jobs must not block the FastAPI event loop — use `AsyncScheduler` or run jobs in a thread pool
- httpx requests must use async — do not use the synchronous `requests` library
- Handle Ollama being unavailable gracefully — if Ollama is down, log the error and skip classification rather than crashing
- Handle LLM API rate limits gracefully — catch rate limit exceptions and retry with exponential backoff
