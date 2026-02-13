from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
import unittest

from focuslog.db import FocusLogDB, SessionRecord
from focuslog.tests.test_helpers import local_tmp_dir


class TestDBSchema(unittest.TestCase):
    def test_schema_created(self) -> None:
        with local_tmp_dir() as tmp:
            db_path = tmp / "data" / "focuslog.sqlite"
            FocusLogDB(db_path)

            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
                ).fetchone()

            self.assertIsNotNone(row)

    def test_get_session(self) -> None:
        with local_tmp_dir() as tmp:
            db = FocusLogDB(tmp / "data" / "focuslog.sqlite")
            now = datetime.now(tz=timezone.utc)
            db.add_session(
                SessionRecord(
                    start_time=now,
                    end_time=now + timedelta(minutes=1),
                    duration_sec=60,
                    task="测试",
                    tags="a,b",
                    kind="work",
                    completed=True,
                    interrupted_reason=None,
                )
            )
            listed = db.list_sessions(limit=1)
            loaded = db.get_session(listed[0].id)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.task, "测试")


if __name__ == "__main__":
    unittest.main()
