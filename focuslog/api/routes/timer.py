from __future__ import annotations

import json
import queue
from typing import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ...timer import TimerConfig
from ..timer_service import build_config, timer_service

router = APIRouter(prefix="/api/v1", tags=["timer"])


class TimerStartRequest(BaseModel):
    task: str = ""
    tags: str = ""
    work_minutes: float = Field(default=25.0, ge=0)
    break_minutes: float = Field(default=5.0, ge=0)
    long_break_minutes: float = Field(default=15.0, ge=0)
    cycles: int = Field(default=4, ge=1)
    tick_seconds: float = Field(default=1.0, ge=0)
    sound: bool = True
    notify: bool = False


@router.post("/timer/start")
def start_timer(payload: TimerStartRequest) -> dict[str, object]:
    config: TimerConfig = build_config(payload.model_dump())
    state = timer_service.start(config)
    return vars(state)


@router.post("/timer/stop")
def stop_timer() -> dict[str, object]:
    return vars(timer_service.stop())


@router.get("/timer/state")
def timer_state() -> dict[str, object]:
    return vars(timer_service.state())


@router.get("/timer/stream")
def timer_stream() -> StreamingResponse:
    subscriber = timer_service.subscribe()

    def event_iter() -> Iterator[str]:
        try:
            while True:
                try:
                    event = subscriber.get(timeout=10)
                    yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            timer_service.unsubscribe(subscriber)

    return StreamingResponse(event_iter(), media_type="text/event-stream")

