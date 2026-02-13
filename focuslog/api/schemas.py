from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class SessionOut(BaseModel):
    id: int
    start_time: datetime
    end_time: datetime
    duration_sec: int
    task: str
    tags: str
    kind: str
    completed: bool
    interrupted_reason: str | None = None


class StatsWindowOut(BaseModel):
    work_sec: int
    break_sec: int
    work_sessions: int
    completed_work_sessions: int
    interrupted_sessions: int


class StatsOut(BaseModel):
    today: StatsWindowOut
    this_week: StatsWindowOut
    last_7_days: StatsWindowOut


class FileResult(BaseModel):
    path: str


class HealthOut(BaseModel):
    status: str = Field(default="ok")


class MetaOut(BaseModel):
    app: str
    version: str
    db_path: str
    platform: str

