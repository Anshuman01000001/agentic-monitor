import logging
from apscheduler.schedulers.background import BackgroundScheduler
from config.settings import settings
from monitors.device_monitor import collect_device_metrics
from monitors.website_monitor import check_website
from pipeline.collector import save_event
from agent.escalator import process_event_sync
import asyncio

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


def start_scheduler(app=None):
    # device check job (sync)
    def device_job():
        try:
            metrics = collect_device_metrics()
            # Save each metric as a separate Event
            for metric_name, metric_value in metrics.items():
                if isinstance(metric_value, (int, float)):
                    save_event(
                        source_type="device",
                        source_name="localhost",
                        metric_name=metric_name,
                        metric_value=float(metric_value),
                        raw_data=metrics,
                    )
                    # process event asynchronously/safely
                    try:
                        # collector.save_event returns the Event but we don't have it here; call process_event_sync with last saved event id if needed
                        # For simplicity, call process_event_sync with a fresh read of the most recent event
                        from database import db
                        session = db.get_session()
                        try:
                            ev = session.query(
                                __import__("database.models", fromlist=["Event"]).Event
                            ).order_by(__import__("database.models", fromlist=["Event"]).Event.id.desc()).first()
                            if ev:
                                process_event_sync(ev)
                        finally:
                            session.close()
                    except Exception:
                        logger.exception("Failed to invoke process_event for device metric")
            logger.info("Device metrics collected and saved")
        except Exception as e:
            logger.exception("Device job failed: %s", e)

    def website_job():
        """Run async website checks synchronously."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_async_website_job())
        except Exception as e:
            logger.exception("Website job failed: %s", e)
        finally:
            loop.close()

    async def _async_website_job():
        domains = settings.MONITOR_DOMAINS
        for d in domains:
            try:
                res = await check_website(d)
                # Save status code, response time, SSL days as separate events
                if res.get("status_code"):
                    save_event(
                        source_type="website",
                        source_name=d,
                        metric_name="status_code",
                        metric_value=float(res["status_code"]),
                        raw_data=res,
                    )
                    try:
                        from database import db
                        session = db.get_session()
                        try:
                            ev = session.query(
                                __import__("database.models", fromlist=["Event"]).Event
                            ).order_by(__import__("database.models", fromlist=["Event"]).Event.id.desc()).first()
                            if ev:
                                process_event_sync(ev)
                        finally:
                            session.close()
                    except Exception:
                        logger.exception("Failed to invoke process_event for website status_code")
                if res.get("response_time_ms"):
                    save_event(
                        source_type="website",
                        source_name=d,
                        metric_name="response_time_ms",
                        metric_value=float(res["response_time_ms"]),
                        raw_data=res,
                    )
                    try:
                        from database import db
                        session = db.get_session()
                        try:
                            ev = session.query(
                                __import__("database.models", fromlist=["Event"]).Event
                            ).order_by(__import__("database.models", fromlist=["Event"]).Event.id.desc()).first()
                            if ev:
                                process_event_sync(ev)
                        finally:
                            session.close()
                    except Exception:
                        logger.exception("Failed to invoke process_event for website response_time_ms")
                if res.get("ssl_days_remaining") is not None:
                    save_event(
                        source_type="website",
                        source_name=d,
                        metric_name="ssl_days_remaining",
                        metric_value=float(res["ssl_days_remaining"]),
                        raw_data=res,
                    )
                    try:
                        from database import db
                        session = db.get_session()
                        try:
                            ev = session.query(
                                __import__("database.models", fromlist=["Event"]).Event
                            ).order_by(__import__("database.models", fromlist=["Event"]).Event.id.desc()).first()
                            if ev:
                                process_event_sync(ev)
                        finally:
                            session.close()
                    except Exception:
                        logger.exception("Failed to invoke process_event for website ssl_days_remaining")
                logger.info("Website %s: saved metrics", d)
            except Exception:
                logger.exception("Website check failed for %s", d)

    scheduler.add_job(
        device_job, 'interval', seconds=settings.DEVICE_CHECK_INTERVAL, id='device_job'
    )
    scheduler.add_job(
        website_job,
        'interval',
        seconds=settings.WEBSITE_CHECK_INTERVAL,
        id='website_job',
    )
    scheduler.start()
    logger.info("Scheduler started with device interval=%ds, website interval=%ds",
                settings.DEVICE_CHECK_INTERVAL, settings.WEBSITE_CHECK_INTERVAL)
