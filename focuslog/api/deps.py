from __future__ import annotations

from pathlib import Path

from fastapi import Request

from ..db import FocusLogDB


def get_db(request: Request) -> FocusLogDB:
    db_path = Path(request.app.state.db_path)
    return FocusLogDB(db_path)

