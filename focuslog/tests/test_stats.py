from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from focuslog.db import FocusLogDB, SessionRecord
from focuslog.reporting import build_stats
from focuslog.tests.test_helpers import local_tmp_dir


class TestStats(unittest.TestCase):
    def test_stats_aggregation(self) -> None:
        with local_tmp_dir() as tmp:
            db = FocusLogDB(tmp / "focuslog.sqlite")
            now = datetime(2026, 2, 13, 12, 0, tzinfo=timezone.utc)

            db.add_session(
                SessionRecord(
                    start_time=now - timedelta(hours=2),
                    end_time=now - timedelta(hours=1, minutes=30),
                    duration_sec=1800,
                    task="任务A",
                    tags="学习",
                    kind="work",
                    completed=True,
                )
            )
            db.add_session(
                SessionRecord(
                    start_time=now - timedelta(hours=1, minutes=20),
                    end_time=now - timedelta(hours=1, minutes=15),
                    duration_sec=300,
                    task="任务A",
                    tags="学习",
                    kind="break",
                    completed=True,
                )
            )
            db.add_session(
                SessionRecord(
                    start_time=now - timedelta(days=1, hours=1),
                    end_time=now - timedelta(days=1, minutes=40),
                    duration_sec=1200,
                    task="任务B",
                    tags="项目",
                    kind="work",
                    completed=True,
                )
            )
            db.add_session(
                SessionRecord(
                    start_time=now - timedelta(minutes=20),
                    end_time=now - timedelta(minutes=18),
                    duration_sec=120,
                    task="任务C",
                    tags="项目",
                    kind="work",
                    completed=False,
                    interrupted_reason="Ctrl-C",
                )
            )
            db.add_session(
                SessionRecord(
                    start_time=now - timedelta(days=8),
                    end_time=now - timedelta(days=8, minutes=-10),
                    duration_sec=600,
                    task="旧任务",
                    tags="历史",
                    kind="work",
                    completed=True,
                )
            )

            stats = build_stats(db, now=now)

            self.assertEqual(stats["today"].work_sec, 1920)
            self.assertEqual(stats["today"].break_sec, 300)
            self.assertEqual(stats["today"].work_sessions, 2)
            self.assertEqual(stats["today"].completed_work_sessions, 1)
            self.assertEqual(stats["today"].interrupted_sessions, 1)

            self.assertEqual(stats["this_week"].work_sec, 3120)
            self.assertEqual(stats["last_7_days"].work_sec, 3120)


if __name__ == "__main__":
    unittest.main()
