from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from ...db import FocusLogDB
from ..deps import get_db
from ..schemas import SessionOut

router = APIRouter(prefix="/api/v1", tags=["sessions"])


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    since: datetime | None = None,
    tag: str | None = None,
    task_contains: str | None = None,
    limit: int = Query(default=30, ge=1, le=2000),
    db: FocusLogDB = Depends(get_db),
) -> list[SessionOut]:
    items = db.list_sessions(since=since, tag=tag, task_contains=task_contains, limit=limit)
    return [SessionOut(**vars(item)) for item in items]


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: FocusLogDB = Depends(get_db)) -> SessionOut:
    item = db.get_session(session_id)
    if item is not None:
        return SessionOut(**vars(item))
    raise HTTPException(status_code=404, detail="session not found")

