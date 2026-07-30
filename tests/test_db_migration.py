import os
import sqlite3
import tempfile
import unittest

from database import db


class DatabaseMigrationTest(unittest.TestCase):
    def test_init_db_adds_missing_columns_for_existing_sqlite_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_monitor.db")
            database_url = f"sqlite:///{db_path}"

            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE events (id INTEGER PRIMARY KEY, timestamp TEXT, source_type TEXT, source_name TEXT, metric_name TEXT, metric_value REAL, classification TEXT, confidence REAL, escalated INTEGER, raw_data TEXT)"
            )
            conn.commit()
            conn.close()

            db.init_db(database_url)

            conn = sqlite3.connect(db_path)
            columns = [row[1] for row in conn.execute("PRAGMA table_info(events)")]
            conn.close()

            self.assertIn("reason", columns)


if __name__ == "__main__":
    unittest.main()
