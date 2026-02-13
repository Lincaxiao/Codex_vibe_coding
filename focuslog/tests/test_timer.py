from __future__ import annotations

from datetime import datetime, timezone
import io
import unittest

from focuslog.clock import FakeClock
from focuslog.db import FocusLogDB
from focuslog.notifier import Notifier
from focuslog.tests.test_helpers import local_tmp_dir
from focuslog.timer import PomodoroRunner, TimerConfig


class TestTimer(unittest.TestCase):
    def test_completed_work_cycle_logged(self) -> None:
        with local_tmp_dir() as tmp:
            db = FocusLogDB(tmp / "focuslog.sqlite")
            clock = FakeClock(start=datetime(2026, 2, 13, 10, 0, tzinfo=timezone.utc))
            output = io.StringIO()
            runner = PomodoroRunner(db=db, clock=clock, notifier=Notifier(stream=output), stream=output)

            result = runner.run(
                TimerConfig(
                    task="写文档",
                    tags="学习,复盘",
                    work_minutes=0.05,
                    break_minutes=0,
                    long_break_minutes=0,
                    cycles=1,
                    tick_seconds=1,
                    sound=False,
                    notify=False,
                )
            )

            self.assertFalse(result.interrupted)
            sessions = db.list_all_sessions()
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0].kind, "work")
            self.assertTrue(sessions[0].completed)
            self.assertEqual(sessions[0].duration_sec, 3)

    def test_interruption_logged(self) -> None:
        with local_tmp_dir() as tmp:
            db = FocusLogDB(tmp / "focuslog.sqlite")
            clock = FakeClock(
                start=datetime(2026, 2, 13, 10, 0, tzinfo=timezone.utc),
                interrupt_on_sleep_call=1,
            )
            output = io.StringIO()
            runner = PomodoroRunner(db=db, clock=clock, notifier=Notifier(stream=output), stream=output)

            result = runner.run(
                TimerConfig(
                    task="编码",
                    tags="项目",
                    work_minutes=0.1,
                    break_minutes=0,
                    long_break_minutes=0,
                    cycles=1,
                    tick_seconds=1,
                    sound=False,
                    notify=False,
                )
            )

            self.assertTrue(result.interrupted)
            sessions = db.list_all_sessions()
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0].kind, "work")
            self.assertFalse(sessions[0].completed)
            self.assertEqual(sessions[0].interrupted_reason, "Ctrl-C")

    def test_manual_stop_logged(self) -> None:
        with local_tmp_dir() as tmp:
            db = FocusLogDB(tmp / "focuslog.sqlite")
            clock = FakeClock(start=datetime(2026, 2, 13, 10, 0, tzinfo=timezone.utc))
            output = io.StringIO()
            holder: dict[str, PomodoroRunner] = {}

            def on_progress(event: str, _: dict[str, object]) -> None:
                if event == "tick":
                    holder["runner"].request_stop()

            runner = PomodoroRunner(
                db=db,
                clock=clock,
                notifier=Notifier(stream=output),
                stream=output,
                progress_callback=on_progress,
            )
            holder["runner"] = runner

            result = runner.run(
                TimerConfig(
                    task="手动停止测试",
                    tags="gui",
                    work_minutes=0.2,
                    break_minutes=0,
                    long_break_minutes=0,
                    cycles=1,
                    tick_seconds=1,
                    sound=False,
                    notify=False,
                )
            )

            self.assertTrue(result.interrupted)
            sessions = db.list_all_sessions()
            self.assertEqual(len(sessions), 1)
            self.assertFalse(sessions[0].completed)
            self.assertEqual(sessions[0].interrupted_reason, "手动停止")


if __name__ == "__main__":
    unittest.main()
