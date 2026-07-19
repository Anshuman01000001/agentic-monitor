import os
import tempfile
import unittest
from unittest import mock


class TestIntegrationProcessEvent(unittest.TestCase):
    def setUp(self):
        # create a temporary sqlite file for DB
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test_monitor.db")
        self.db_url = f"sqlite:///{self.db_path}"

    def tearDown(self):
        self.tmpdir.cleanup()

    def _require_sqlalchemy(self):
        try:
            import sqlalchemy  # noqa: F401
            return True
        except Exception:
            return False

    def test_end_to_end_escalation_creates_alert(self):
        if not self._require_sqlalchemy():
            self.skipTest("sqlalchemy not installed")

        # Lazy imports to avoid failing when deps are not installed
        from database import db
        from pipeline.collector import save_event
        from database.models import Event, Alert

        # initialize DB
        db.init_db(self.db_url)

        # create an event
        ev = save_event("device", "localhost", "cpu_percent", 99.0, raw_data={})

        # Patch classifier to return critical
        import agent.classifier as classifier_mod
        import agent.rag as rag_mod
        import agent.alert_generator as alert_mod
        import notifications.email_notifier as email_mod
        import agent.escalator as escalator_mod

        with mock.patch.object(classifier_mod, 'classify_event_with_ollama', return_value={'classification':'critical','confidence':0.95,'reason':'over threshold'}) , \
             mock.patch.object(rag_mod, 'get_runbook_context', return_value='Runbook action'), \
             mock.patch.object(alert_mod, 'generate_alert_text', return_value='Take action now'), \
             mock.patch.object(email_mod, 'send_email', return_value=True):
            # reload event from DB to get a proper ORM instance
            session = db.get_session()
            try:
                ev_db = session.query(Event).get(ev.id)
            finally:
                session.close()

            # Call escalator
            escalator_mod.process_event_sync(ev_db)

            # Assert an Alert was created
            session = db.get_session()
            try:
                alerts = session.query(Alert).filter(Alert.event_id == ev.id).all()
                self.assertGreaterEqual(len(alerts), 1)
            finally:
                session.close()

    def test_consecutive_warnings_escalate(self):
        if not self._require_sqlalchemy():
            self.skipTest("sqlalchemy not installed")

        from database import db
        from database.models import Event, Alert
        from pipeline.collector import save_event
        import agent.classifier as classifier_mod
        import agent.rag as rag_mod
        import agent.alert_generator as alert_mod
        import notifications.email_notifier as email_mod
        import agent.escalator as escalator_mod
        from config import settings

        db.init_db(self.db_url)

        # Insert N previous warning events for same source
        n = settings.CONSECUTIVE_WARNINGS_BEFORE_ALERT
        for _ in range(n):
            e = save_event("device", "hostX", "cpu_percent", 80.0, raw_data={})
            # manually mark as warning
            session = db.get_session()
            try:
                ev = session.query(Event).get(e.id)
                ev.classification = 'warning'
                session.add(ev)
                session.commit()
            finally:
                session.close()

        # Now create a new event which classifier will mark as warning
        ev_new = save_event("device", "hostX", "cpu_percent", 81.0, raw_data={})

        with mock.patch.object(classifier_mod, 'classify_event_with_ollama', return_value={'classification':'warning','confidence':0.6,'reason':'elevated'}) , \
             mock.patch.object(rag_mod, 'get_runbook_context', return_value='Recommended action'), \
             mock.patch.object(alert_mod, 'generate_alert_text', return_value='Please act'), \
             mock.patch.object(email_mod, 'send_email', return_value=True):
            session = db.get_session()
            try:
                ev_db = session.query(Event).get(ev_new.id)
            finally:
                session.close()

            escalator_mod.process_event_sync(ev_db)

            # Check alert created
            session = db.get_session()
            try:
                alerts = session.query(Alert).filter(Alert.event_id == ev_new.id).all()
                self.assertGreaterEqual(len(alerts), 1)
            finally:
                session.close()


if __name__ == "__main__":
    unittest.main()
