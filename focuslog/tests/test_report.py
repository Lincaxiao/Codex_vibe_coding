from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from focuslog.db import FocusLogDB, SessionRecord
from focuslog.reporting import generate_weekly_report
from focuslog.tests.test_helpers import local_tmp_dir


class TestReport(unittest.TestCase):
    def test_generate_weekly_report_markdown(self) -> None:
        with local_tmp_dir() as tmp:
            db = FocusLogDB(tmp / "focuslog.sqlite")
            out_dir = tmp / "out"
            now = datetime(2026, 2, 13, 12, 0, tzinfo=timezone.utc)

            db.add_session(
                SessionRecord(
                    start_time=datetime(2026, 2, 10, 9, 0, tzinfo=timezone.utc),
                    end_time=datetime(2026, 2, 10, 9, 30, tzinfo=timezone.utc),
                    duration_sec=1800,
                    task="写论文",
                    tags="研究,写作",
                    kind="work",
                    completed=True,
                )
            )
            db.add_session(
                SessionRecord(
                    start_time=datetime(2026, 2, 12, 14, 0, tzinfo=timezone.utc),
                    end_time=datetime(2026, 2, 12, 14, 20, tzinfo=timezone.utc),
                    duration_sec=1200,
                    task="看文献",
                    tags="研究",
                    kind="work",
                    completed=True,
                )
            )
            db.add_session(
                SessionRecord(
                    start_time=now - timedelta(days=10),
                    end_time=now - timedelta(days=10, minutes=-10),
                    duration_sec=600,
                    task="周外任务",
                    tags="无",
                    kind="work",
                    completed=True,
                )
            )

            report_path = generate_weekly_report(
                db=db,
                out_dir=out_dir,
                year=2026,
                week=7,
                now=now,
            )

            self.assertTrue(report_path.exists())
            content = report_path.read_text(encoding="utf-8")
            self.assertIn("# FocusLog 周报 2026-W07", content)
            self.assertIn("写论文", content)
            self.assertNotIn("周外任务", content)


if __name__ == "__main__":
    unittest.main()
