from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...db import FocusLogDB
from ...exporting import export_sessions_csv
from ..deps import get_db
from ..schemas import FileResult

router = APIRouter(prefix="/api/v1", tags=["export"])


class ExportCsvRequest(BaseModel):
    out_dir: str | None = None


@router.post("/export/csv", response_model=FileResult)
def export_csv(payload: ExportCsvRequest, db: FocusLogDB = Depends(get_db)) -> FileResult:
    out_dir = Path(payload.out_dir) if payload.out_dir else Path(__file__).resolve().parents[2] / "out"
    csv_path = export_sessions_csv(db, out_dir)
    return FileResult(path=str(csv_path))

