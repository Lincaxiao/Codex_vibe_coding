from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import sys
from typing import Callable, TextIO

from .clock import Clock
from .db import FocusLogDB, SessionRecord
from .notifier import Notifier


@dataclass(frozen=True)
class TimerConfig:
    task: str
    tags: str
    work_minutes: float
    break_minutes: float
    long_break_minutes: float
    cycles: int
    tick_seconds: float
    sound: bool
    notify: bool


@dataclass(frozen=True)
class RunResult:
    interrupted: bool
    completed_work_sessions: int
    logged_sessions: int


ProgressCallback = Callable[[str, dict[str, object]], None]


def minutes_to_seconds(minutes: float) -> int:
    if minutes <= 0:
        return 0
    seconds = int(round(minutes * 60))
    return max(1, seconds)


def format_countdown(seconds: int) -> str:
    total = max(0, seconds)
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


class PomodoroRunner:
    def __init__(
        self,
        db: FocusLogDB,
        clock: Clock,
        notifier: Notifier,
        stream: TextIO | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.db = db
        self.clock = clock
        self.notifier = notifier
        self.stream = stream or sys.stdout
        self.progress_callback = progress_callback
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self, config: TimerConfig) -> RunResult:
        self._stop_requested = False
        cycles = max(1, config.cycles)
        completed_work = 0
        logged_sessions = 0
        self._emit(
            "run_start",
            task=config.task,
            tags=config.tags,
            work_minutes=config.work_minutes,
            break_minutes=config.break_minutes,
            long_break_minutes=config.long_break_minutes,
            cycles=cycles,
        )

        self.stream.write(
            f"开始 FocusLog：工作 {config.work_minutes} 分钟，短休息 {config.break_minutes} 分钟，"
            f"长休息 {config.long_break_minutes} 分钟，循环 {cycles} 次\n"
        )
        self.stream.flush()

        for cycle_idx in range(1, cycles + 1):
            done = self._run_interval(
                kind="work",
                label=f"工作 {cycle_idx}/{cycles}",
                duration_sec=minutes_to_seconds(config.work_minutes),
                task=config.task,
                tags=config.tags,
                tick_seconds=config.tick_seconds,
                sound=config.sound,
                notify=config.notify,
            )
            logged_sessions += 1
            if not done:
                self.stream.write("会话已中断，已保存当前记录。\n")
                self.stream.flush()
                self._emit(
                    "run_end",
                    interrupted=True,
                    completed_work_sessions=completed_work,
                    logged_sessions=logged_sessions,
                )
                return RunResult(True, completed_work, logged_sessions)
            completed_work += 1

            if cycle_idx < cycles and config.break_minutes > 0:
                done = self._run_interval(
                    kind="break",
                    label=f"短休息 {cycle_idx}/{cycles}",
                    duration_sec=minutes_to_seconds(config.break_minutes),
                    task=config.task,
                    tags=config.tags,
                    tick_seconds=config.tick_seconds,
                    sound=config.sound,
                    notify=config.notify,
                )
                logged_sessions += 1
                if not done:
                    self.stream.write("休息阶段被中断，已保存当前记录。\n")
                    self.stream.flush()
                    self._emit(
                        "run_end",
                        interrupted=True,
                        completed_work_sessions=completed_work,
                        logged_sessions=logged_sessions,
                    )
                    return RunResult(True, completed_work, logged_sessions)

            if cycle_idx == cycles and cycles > 1 and config.long_break_minutes > 0:
                done = self._run_interval(
                    kind="break",
                    label="长休息",
                    duration_sec=minutes_to_seconds(config.long_break_minutes),
                    task=config.task,
                    tags=config.tags,
                    tick_seconds=config.tick_seconds,
                    sound=config.sound,
                    notify=config.notify,
                )
                logged_sessions += 1
                if not done:
                    self.stream.write("长休息阶段被中断，已保存当前记录。\n")
                    self.stream.flush()
                    self._emit(
                        "run_end",
                        interrupted=True,
                        completed_work_sessions=completed_work,
                        logged_sessions=logged_sessions,
                    )
                    return RunResult(True, completed_work, logged_sessions)

        self.stream.write(f"番茄钟完成：已完成工作会话 {completed_work} 次。\n")
        self.stream.flush()
        self._emit(
            "run_end",
            interrupted=False,
            completed_work_sessions=completed_work,
            logged_sessions=logged_sessions,
        )
        return RunResult(False, completed_work, logged_sessions)

    def _run_interval(
        self,
        kind: str,
        label: str,
        duration_sec: int,
        task: str,
        tags: str,
        tick_seconds: float,
        sound: bool,
        notify: bool,
    ) -> bool:
        start_time = self.clock.now()
        target_time = start_time + timedelta(seconds=duration_sec)
        completed = True
        interrupted_reason: str | None = None
        self._emit(
            "interval_start",
            kind=kind,
            label=label,
            duration_sec=duration_sec,
            start_time=start_time,
        )

        while True:
            if self._stop_requested:
                completed = False
                interrupted_reason = "手动停止"
                break

            now = self.clock.now()
            remaining = (target_time - now).total_seconds()
            if remaining <= 0:
                break

            remaining_int = int(remaining + 0.999)
            self._render(label, remaining_int)
            self._emit(
                "tick",
                kind=kind,
                label=label,
                remaining_sec=remaining_int,
                start_time=start_time,
            )
            sleep_step = remaining if tick_seconds <= 0 else min(remaining, tick_seconds)

            try:
                self.clock.sleep(sleep_step)
            except KeyboardInterrupt:
                completed = False
                interrupted_reason = "Ctrl-C"
                break

        self._clear_line()

        end_time = self.clock.now()
        if completed and end_time < target_time:
            end_time = target_time

        duration = int(round((end_time - start_time).total_seconds()))
        duration = max(0, duration)

        if completed and duration < duration_sec:
            duration = duration_sec
            end_time = start_time + timedelta(seconds=duration_sec)

        self.db.add_session(
            SessionRecord(
                start_time=start_time,
                end_time=end_time,
                duration_sec=duration,
                task=task,
                tags=tags,
                kind=kind,
                completed=completed,
                interrupted_reason=interrupted_reason,
            )
        )

        state_text = "完成" if completed else "中断"
        kind_text = "工作" if kind == "work" else "休息"
        self.stream.write(
            f"{kind_text}阶段：{label}，状态：{state_text}，用时 {format_countdown(duration)}\n"
        )
        if sound and completed:
            self.stream.write("\a")

        if notify:
            notify_msg = "已完成" if completed else "被中断"
            self.notifier.notify("FocusLog", f"{label} {notify_msg}")

        self.stream.flush()
        self._emit(
            "interval_end",
            kind=kind,
            label=label,
            completed=completed,
            duration_sec=duration,
            interrupted_reason=interrupted_reason,
            start_time=start_time,
            end_time=end_time,
        )
        return completed

    def _render(self, label: str, remaining_seconds: int) -> None:
        self.stream.write(f"\r{label} 剩余 {format_countdown(remaining_seconds)}")
        self.stream.flush()

    def _clear_line(self) -> None:
        self.stream.write("\r" + (" " * 80) + "\r")
        self.stream.flush()

    def _emit(self, event: str, **payload: object) -> None:
        if self.progress_callback is None:
            return
        self.progress_callback(event, payload)
