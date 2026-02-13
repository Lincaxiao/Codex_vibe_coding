from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...db import FocusLogDB
from ...reporting import generate_weekly_report
from ..deps import get_db
from ..schemas import FileResult

router = APIRouter(prefix="/api/v1", tags=["report"])


class WeeklyReportRequest(BaseModel):
    year: int | None = None
    week: int | None = None
    out_dir: str | None = None


@router.post("/report/weekly", response_model=FileResult)
def generate_report(payload: WeeklyReportRequest, db: FocusLogDB = Depends(get_db)) -> FileResult:
    out_dir = Path(payload.out_dir) if payload.out_dir else Path(__file__).resolve().parents[2] / "out"
    report_path = generate_weekly_report(
        db=db,
        out_dir=out_dir,
        year=payload.year,
        week=payload.week,
    )
    return FileResult(path=str(report_path))

