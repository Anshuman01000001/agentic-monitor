#!/usr/bin/env python3
"""
Agentic Monitor — End-to-end demo script.

Runs through the full pipeline with no manual steps so you can demo it live:

  1. Initializes the database and ChromaDB RAG store
  2. Collects live device metrics (CPU, memory, disk, network)
  3. Saves them as Events
  4. Classifies each event with the local SLM (Ollama/phi3)
  5. Retrieves the most relevant runbook chunk via RAG
  6. Generates a human-readable alert with the LLM
  7. Sends a real formatted email via SMTP
  8. Prints a final summary with links to the dashboard

Usage:
    .venv/bin/python scripts/demo.py
    .venv/bin/python scripts/demo.py --no-email   # skip the live email
    .venv/bin/python scripts/demo.py --open-browser   # also open the dashboard

Tip: in a second terminal run the dashboard so the demo audience can see it live:
    .venv/bin/uvicorn main:app --port 8000
"""
import argparse
import asyncio
import os
import sys
import time
import webbrowser
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# --- Pretty console output ---------------------------------------------------

def banner(title: str):
    line = "═" * max(60, len(title) + 4)
    print(f"\n{line}\n  {title}\n{line}")


def step(num: int, title: str):
    print(f"\n── Step {num}: {title} " + "─" * (50 - len(title)))


def ok(msg: str):
    print(f"   ✓ {msg}")


def info(msg: str):
    print(f"   ℹ {msg}")


def fail(msg: str):
    print(f"   ✗ {msg}")


# --- Steps -------------------------------------------------------------------

def step1_init():
    step(1, "Initialize database and RAG store")
    from config.settings import settings
    from database import db
    from agent.rag import init_rag_store

    db.init_db(settings.DATABASE_URL)
    ok(f"Database ready at {settings.DATABASE_URL}")
    init_rag_store(settings.CHROMA_PERSIST_DIR)
    ok(f"RAG store ready at {settings.CHROMA_PERSIST_DIR}")


def step2_collect():
    step(2, "Collect live device metrics")
    from monitors.device_monitor import collect_device_metrics
    metrics = collect_device_metrics()
    cpu = metrics.get("cpu_percent")
    mem = metrics.get("memory_percent")
    info(f"CPU:   {cpu}%")
    info(f"Memory: {mem}%")
    disks = metrics.get("disks", [])
    if disks:
        disk_parts = []
        for d in disks:
            mount = d["mountpoint"]
            pct = d["percent"]
            disk_parts.append(f"{mount}={pct}%")
        info("Disks: " + ", ".join(disk_parts))
    return metrics


def step3_save_and_classify(metric_name: str, value: float, source: str = "device/live-demo"):
    from pipeline.collector import save_event
    from agent.classifier import classify_event_with_ollama
    from database.models import Event

    event = save_event(
        source_type=source.split("/")[0],
        source_name=source.split("/", 1)[1],
        metric_name=metric_name,
        metric_value=value,
        raw_data={"collected_at": datetime.utcnow().isoformat()},
    )
    ok(f"Saved Event #{event.id}: {metric_name}={value}")

    print("   ⏳ Classifying with local SLM (Ollama/phi3) ...", end="", flush=True)
    result = asyncio.run(classify_event_with_ollama(event))
    classification = result.get("classification")
    confidence = result.get("confidence")
    reason = result.get("reason")
    print("\r" + " " * 60 + "\r", end="")
    ok(f"Classification: {classification.upper()}  (confidence={confidence:.2f})")
    info(f"Reason: {reason}")
    return event, classification, confidence


def step4_rag(event, classification):
    step(4, "Retrieve runbook context via RAG")
    from agent.rag import get_runbook_context
    query = f"{event.source_type} {event.source_name} {event.metric_name} {event.metric_value}"
    ctx = get_runbook_context(query)
    if ctx:
        ok(f"Retrieved {len(ctx)} chars of runbook context")
        snippet = ctx.replace("\n", " ")[:200]
        info(f"Snippet: {snippet}...")
    else:
        fail("No RAG context retrieved (RAG store not initialized or no runbooks)")
    return ctx


def step5_generate_alert(event, classification, reason, runbook_ctx):
    step(5, "Generate alert text with LLM (Ollama/phi3)")
    from agent.alert_generator import generate_alert_text
    print("   ⏳ Generating alert ...", end="", flush=True)
    text = generate_alert_text(event, runbook_ctx)
    print("\r" + " " * 60 + "\r", end="")
    if text and "(Details unavailable)" not in text:
        ok(f"Generated {len(text)} chars of alert text")
        for line in text.splitlines()[:6]:
            info(line)
    else:
        fail("Fell back to template alert")
    return text


def step6_send_email(event, classification, reason, runbook_ctx, alert_text, do_send: bool):
    step(6, "Send formatted email alert")
    if not do_send:
        info("Skipped (--no-email). Alert would be sent to your SMTP recipient.")
        return True

    from notifications.email_notifier import render_alert, send_email

    details = {
        "source_type": event.source_type,
        "source_name": event.source_name,
        "metric_name": event.metric_name,
        "metric_value": event.metric_value,
        "classification": classification,
        "confidence": event.confidence,
        "timestamp": event.timestamp.isoformat() if event.timestamp else "",
    }
    html_body, text_body = render_alert(details, alert_text, runbook_ctx, reason)
    subject = f"[{classification.upper()}] {event.source_name} — {event.metric_name}"
    print("   ⏳ Sending via SMTP ...", end="", flush=True)
    sent = send_email(subject=subject, html_body=html_body, text_body=text_body)
    print("\r" + " " * 60 + "\r", end="")
    if sent:
        ok(f"Email sent: \"{subject}\"")
        return True
    fail("Email send failed — check SMTP settings in .env")
    return False


def step7_summary(events, escalated_count, email_sent):
    step(7, "Summary")
    from config.settings import settings

    print(f"   Events processed:    {len(events)}")
    print(f"   Escalated to alert:  {escalated_count}")
    print(f"   Email delivered:     {'yes' if email_sent else 'no'}")
    print()
    print(f"   📊 Dashboard:    http://localhost:8000")
    print(f"   📊 Events API:   http://localhost:8000/api/events?limit=20")
    print(f"   📊 Alerts API:   http://localhost:8000/api/alerts?limit=20")
    print(f"   📧 Alerts go to: {settings.ALERT_EMAIL_TO}")


# --- Main --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run a full end-to-end demo of the Agentic Monitor.")
    parser.add_argument("--no-email", action="store_true", help="Don't send a real email.")
    parser.add_argument("--open-browser", action="store_true", help="Open the dashboard in your browser.")
    args = parser.parse_args()

    banner("Agentic Monitor — End-to-End Demo")
    info(f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1) Init
    step1_init()

    # 2) Collect real metrics
    metrics = step2_collect()

    # 3) Save + classify a representative event
    event, classification, confidence = step3_save_and_classify(
        metric_name="cpu_percent",
        value=float(metrics.get("cpu_percent", 50.0)),
        source="device/live-demo",
    )

    # 4) RAG
    runbook_ctx = step4_rag(event, classification)

    # 5) LLM alert
    from database import db as _db
    session = _db.get_session()
    try:
        ev_db = session.get(__import__("database.models", fromlist=["Event"]).Event, event.id)
        reason = getattr(ev_db, "reason", "") or ""
    finally:
        session.close()
    alert_text = step5_generate_alert(event, classification, reason, runbook_ctx)

    # 6) Email
    email_sent = step6_send_email(
        event, classification, reason, runbook_ctx, alert_text, do_send=not args.no_email
    )

    # 7) Summary
    step7_summary([event], 1, email_sent)

    if args.open_browser:
        webbrowser.open("http://localhost:8000")
        info("Opened dashboard in your default browser.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDemo cancelled.")
        sys.exit(1)
