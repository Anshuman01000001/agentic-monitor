import logging
from datetime import datetime
from database.models import Event
from database import db

logger = logging.getLogger(__name__)


def save_event(
    source_type: str,
    source_name: str,
    metric_name: str,
    metric_value: float,
    raw_data: dict = None,
) -> Event:
    """
    Normalize monitor output and save as Event record.
    
    Args:
        source_type: "device" or "website"
        source_name: hostname or domain
        metric_name: name of the metric (e.g. "cpu_percent", "response_time_ms")
        metric_value: numeric value
        raw_data: optional raw snapshot as dict
    
    Returns:
        Event record (persisted to DB)
    """
    session = db.get_session()
    try:
        event = Event(
            timestamp=datetime.utcnow(),
            source_type=source_type,
            source_name=source_name,
            metric_name=metric_name,
            metric_value=metric_value,
            classification=None,
            confidence=None,
            escalated=False,
            raw_data=raw_data or {},
        )
        session.add(event)
        session.commit()
        logger.debug(
            "Event saved: %s/%s=%s", source_type, metric_name, metric_value
        )
        return event
    except Exception as e:
        session.rollback()
        logger.exception("Failed to save event: %s", e)
        raise
    finally:
        session.close()


def get_recent_events(limit: int = 50) -> list:
    """Fetch most recent events."""
    session = db.get_session()
    try:
        events = session.query(Event).order_by(Event.id.desc()).limit(limit).all()
        return list(reversed(events))
    finally:
        session.close()
