#!/usr/bin/env python3
"""Small CLI helper to create an `Event` and run the agent escalator flow.

Usage examples:
  python scripts/trigger_event.py --source_type device --source_name localhost --metric_name cpu_percent --metric_value 99.9
  python scripts/trigger_event.py --raw '{"example": true}'
"""
import argparse
import json
import logging
import sys

logger = logging.getLogger("trigger_event")


def main():
    parser = argparse.ArgumentParser(description="Trigger an Event and run escalator flow")
    parser.add_argument("--source_type", default="device")
    parser.add_argument("--source_name", default="localhost")
    parser.add_argument("--metric_name", default="test_metric")
    parser.add_argument("--metric_value", type=float, default=0.0)
    parser.add_argument("--raw", default=None, help="Raw JSON for raw_data")
    parser.add_argument("--no-escalate", action="store_true", help="Save event but don't invoke escalator")
    args = parser.parse_args()

    # initialize DB and save event
    try:
        from config.settings import settings
        from database import db
        from pipeline.collector import save_event
    except Exception as e:
        logger.exception("Missing core modules: %s", e)
        sys.exit(2)

    db.init_db(getattr(settings, "DATABASE_URL", "sqlite:///./monitor.db"))

    raw_data = {}
    if args.raw:
        try:
            raw_data = json.loads(args.raw)
        except Exception:
            logger.warning("Could not parse --raw as JSON; using raw string")
            raw_data = {"raw": args.raw}

    ev = save_event(
        source_type=args.source_type,
        source_name=args.source_name,
        metric_name=args.metric_name,
        metric_value=args.metric_value,
        raw_data=raw_data,
    )

    print(f"Saved Event id={ev.id}")

    if args.no_escalate:
        print("Skipping escalator as requested")
        return

    # Try to run the escalator synchronously
    try:
        from agent.escalator import process_event_sync
        from database.models import Event as EventModel
        # reload ORM event and invoke
        from database import db as _db
        session = _db.get_session()
        try:
            event_obj = session.query(EventModel).get(ev.id)
        finally:
            session.close()

        if event_obj is None:
            logger.error("Could not reload Event from DB")
            sys.exit(3)

        process_event_sync(event_obj)
        print("process_event_sync invoked")
    except Exception:
        logger.exception("Failed to run escalator")
        sys.exit(4)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
