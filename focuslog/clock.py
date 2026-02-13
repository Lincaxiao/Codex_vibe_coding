from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        ...

    def sleep(self, seconds: float) -> None:
        ...


class RealClock:
    def now(self) -> datetime:
        return datetime.now().astimezone()

    def sleep(self, seconds: float) -> None:
        time.sleep(max(0.0, seconds))


class FakeClock:
    def __init__(
        self,
        start: datetime | None = None,
        interrupt_on_sleep_call: int | None = None,
    ) -> None:
        base = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        self._current = base
        self._interrupt_on_sleep_call = interrupt_on_sleep_call
        self._sleep_calls = 0

    def now(self) -> datetime:
        return self._current

    def sleep(self, seconds: float) -> None:
        self._sleep_calls += 1
        if (
            self._interrupt_on_sleep_call is not None
            and self._sleep_calls >= self._interrupt_on_sleep_call
        ):
            raise KeyboardInterrupt
        self._current += timedelta(seconds=max(0.0, seconds))
