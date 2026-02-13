from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import queue
from threading import Lock, Thread
from typing import Any

from ..clock import RealClock
from ..db import FocusLogDB, default_db_path, normalize_tags
from ..notifier import Notifier
from ..timer import PomodoroRunner, TimerConfig


@dataclass
class TimerState:
    status: str = "idle"
    stage: str = "等待开始"
    remaining_sec: int = 0
    detail: str = ""
    completed_work_sessions: int = 0
    last_event: dict[str, Any] = field(default_factory=dict)


class TimerService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._runner: PomodoroRunner | None = None
        self._worker: Thread | None = None
        self._state = TimerState()
        self._db_path = default_db_path()
        self._subscribers: list[queue.Queue[dict[str, Any]]] = []

    def configure(self, db_path: Path) -> None:
        with self._lock:
            self._db_path = Path(db_path)

    def state(self) -> TimerState:
        with self._lock:
            return TimerState(**vars(self._state))

    def start(self, config: TimerConfig) -> TimerState:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return TimerState(**vars(self._state))

            self._state = TimerState(status="running", detail="计时进行中")
            self._runner = PomodoroRunner(
                db=FocusLogDB(self._db_path),
                clock=RealClock(),
                notifier=Notifier(),
                progress_callback=self._on_event,
            )
            self._worker = Thread(target=self._runner.run, args=(config,), daemon=True)
            self._worker.start()
            self._broadcast({"event": "state", "status": "running"})
            return TimerState(**vars(self._state))

    def stop(self) -> TimerState:
        with self._lock:
            if self._runner is not None:
                self._runner.request_stop()
                self._state.status = "stopping"
                self._state.detail = "收到停止请求"
                self._broadcast({"event": "state", "status": "stopping"})
            return TimerState(**vars(self._state))

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=200)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers = [item for item in self._subscribers if item is not q]

    def _broadcast(self, event: dict[str, Any]) -> None:
        alive: list[queue.Queue[dict[str, Any]]] = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
                alive.append(q)
            except queue.Full:
                continue
        self._subscribers = alive

    def _on_event(self, event: str, payload: dict[str, Any]) -> None:
        with self._lock:
            normalized = {"event": event, **payload}
            self._state.last_event = normalized
            if event == "tick":
                self._state.stage = str(payload.get("label", ""))
                self._state.remaining_sec = int(payload.get("remaining_sec", 0))
            elif event == "run_end":
                self._state.status = "idle"
                self._state.stage = "空闲"
                self._state.remaining_sec = 0
                self._state.completed_work_sessions = int(payload.get("completed_work_sessions", 0))
                self._state.detail = "已结束"
                self._runner = None
                self._worker = None
            elif event == "runner_error":
                self._state.status = "error"
                self._state.detail = str(payload.get("message", "未知错误"))
            self._broadcast(normalized)


timer_service = TimerService()


def build_config(payload: dict[str, Any]) -> TimerConfig:
    return TimerConfig(
        task=str(payload.get("task", "")).strip(),
        tags=normalize_tags(str(payload.get("tags", ""))),
        work_minutes=float(payload.get("work_minutes", 25)),
        break_minutes=float(payload.get("break_minutes", 5)),
        long_break_minutes=float(payload.get("long_break_minutes", 15)),
        cycles=int(payload.get("cycles", 4)),
        tick_seconds=float(payload.get("tick_seconds", 1)),
        sound=bool(payload.get("sound", True)),
        notify=bool(payload.get("notify", False)),
    )

