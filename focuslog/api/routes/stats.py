from __future__ import annotations

from fastapi import APIRouter, Depends

from ...db import FocusLogDB
from ...reporting import build_stats
from ..deps import get_db
from ..schemas import StatsOut, StatsWindowOut

router = APIRouter(prefix="/api/v1", tags=["stats"])


@router.get("/stats", response_model=StatsOut)
def get_stats(db: FocusLogDB = Depends(get_db)) -> StatsOut:
    stats = build_stats(db)

    def _window(key: str) -> StatsWindowOut:
        w = stats[key]
        return StatsWindowOut(
            work_sec=w.work_sec,
            break_sec=w.break_sec,
            work_sessions=w.work_sessions,
            completed_work_sessions=w.completed_work_sessions,
            interrupted_sessions=w.interrupted_sessions,
        )

    return StatsOut(
        today=_window("today"),
        this_week=_window("this_week"),
        last_7_days=_window("last_7_days"),
    )

