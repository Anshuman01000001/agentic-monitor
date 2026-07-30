import logging
import asyncio
import threading
from datetime import datetime, timedelta
from typing import Optional
from config.settings import settings
from database import db
from database.models import Event, Alert
from agent import classifier as classifier_mod
from agent import rag as rag_mod
from agent import alert_generator as alert_generator_mod
from notifications import email_notifier

logger = logging.getLogger(__name__)


async def _escalate(event: Event, reason: str, runbook_ctx: str, alert_text: str, email_to: Optional[str] = None):
    session = db.get_session()
    try:
        # mark event as escalated
        ev = session.query(Event).get(event.id)
        if ev:
            ev.escalated = True
            session.add(ev)
        # build a human-readable email (structured HTML + plain-text fallback)
        src = ev or event
        details = {
            "source_type": getattr(src, "source_type", ""),
            "source_name": getattr(src, "source_name", ""),
            "metric_name": getattr(src, "metric_name", ""),
            "metric_value": getattr(src, "metric_value", ""),
            "classification": getattr(src, "classification", None),
            "confidence": getattr(src, "confidence", None),
            "timestamp": getattr(src, "timestamp", "").isoformat() if getattr(src, "timestamp", None) else "",
        }
        html_body, text_body = email_notifier.render_alert(details, alert_text, runbook_ctx, reason)
        subject = f"[{(details['classification'] or 'ALERT').upper()}] {event.source_name} — {event.metric_name}"
        sent = email_notifier.send_email(subject=subject, html_body=html_body, to=email_to, text_body=text_body)
        alert = Alert(
            event_id=event.id,
            alert_text=alert_text,
            runbook_context=runbook_ctx,
            email_sent_to=email_to or settings.ALERT_EMAIL_TO,
            email_sent_at=datetime.utcnow() if sent else None,
        )
        session.add(alert)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to write alert record or send email for event %s", event.id)
    finally:
        session.close()


async def process_event(event: Event) -> None:
    """Orchestrate classification, RAG lookup, alert generation and notification for a single Event.

    This function is safe to call concurrently. It writes classification back to DB and may create Alert records.
    """
    # Step 1: classify
    try:
        cls = await classifier_mod.classify_event_with_ollama(event)
    except Exception:
        logger.exception("Classifier failed for event %s", getattr(event, "id", None))
        cls = {"classification": "normal", "confidence": 0.0, "reason": "classification error"}

    classification = cls.get("classification", "normal")
    confidence = float(cls.get("confidence", 0.0))

    # Always ensure event record exists and is updated (classification already written by classifier)

    # Helper: escalate path
    async def _do_escalation(ev: Event):
        runbook_ctx = rag_mod.get_runbook_context(f"{ev.source_type} {ev.source_name} {ev.metric_name} {ev.metric_value} {ev.raw_data}")
        alert_text = alert_generator_mod.generate_alert_text(ev, runbook_ctx)
        await _escalate(ev, cls.get("reason", ""), runbook_ctx, alert_text)

    # Alert storm prevention: check alerts in last 10 minutes
    session = db.get_session()
    try:
        ten_min_ago = datetime.utcnow() - timedelta(minutes=10)
        recent_alerts_count = session.query(Alert).filter(Alert.email_sent_at != None, Alert.email_sent_at >= ten_min_ago, Alert.event_id == event.id).count()
    except Exception:
        recent_alerts_count = 0
    finally:
        session.close()

    # If critical and confidence threshold
    if classification == "critical" and confidence > settings.SLM_CRITICAL_CONFIDENCE_THRESHOLD:
        # storm suppression: if more than 3 alerts for same source in 10 minutes, send storm notification instead
        session = db.get_session()
        try:
            ten_min_ago = datetime.utcnow() - timedelta(minutes=10)
            storms = (
                session.query(Alert)
                .join(Event, Alert.event_id == Event.id)
                .filter(Alert.email_sent_at != None, Alert.email_sent_at >= ten_min_ago, Event.source_name == event.source_name)
                .count()
            )
        except Exception:
            logger.exception("Failed counting recent alerts for storm prevention")
            storms = 0
        finally:
            session.close()

        if storms >= 3:
            logger.info("Alert storm detected for %s; sending storm notification and suppressing further alerts", event.source_name)
            email_notifier.send_email(subject=f"[ALERT STORM] {event.source_name}", html_body=f"Alert storm detected for {event.source_name}. Suppressing further alerts.")
            return

        # escalate
        await _do_escalation(event)
        return

    # If warning: check consecutive warnings
    if classification == "warning":
        session = db.get_session()
        try:
            n = settings.CONSECUTIVE_WARNINGS_BEFORE_ALERT
            required_previous = max(0, n - 1)
            previous_warnings = (
                session.query(Event)
                .filter(Event.source_name == event.source_name, Event.id != event.id)
                .order_by(Event.id.desc())
                .limit(required_previous)
                .all()
            )
            if len(previous_warnings) >= required_previous and all((e.classification == "warning") for e in previous_warnings):
                logger.info("%d consecutive warnings for %s — escalating as critical", n, event.source_name)
                await _do_escalation(event)
                return
            else:
                logger.debug("Warning logged for %s", event.source_name)
        except Exception:
            logger.exception("Failed checking consecutive warnings")
        finally:
            session.close()

    # For normal or non-escalated warning, nothing else to do
    logger.debug("Event processed with classification=%s confidence=%s", classification, confidence)


def process_event_sync(event: Event) -> None:
    """Synchronous wrapper for use from scheduler threads and async contexts."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(process_event(event))
        except Exception:
            logger.exception("process_event_sync failed for event %s", getattr(event, "id", None))
        return

    error: Optional[Exception] = None

    def _run_in_thread() -> None:
        nonlocal error
        try:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                loop.run_until_complete(process_event(event))
            finally:
                loop.close()
                asyncio.set_event_loop(None)
        except Exception as exc:
            error = exc

    thread = threading.Thread(target=_run_in_thread, daemon=True)
    thread.start()
    thread.join()
    if error is not None:
        logger.exception("process_event_sync failed for event %s", getattr(event, "id", None))
        raise error

