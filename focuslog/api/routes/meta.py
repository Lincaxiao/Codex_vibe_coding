from __future__ import annotations

import platform
from pathlib import Path

from fastapi import APIRouter, Request

from ... import __version__
from ..schemas import MetaOut

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/meta", response_model=MetaOut)
def meta(request: Request) -> MetaOut:
    return MetaOut(
        app="FocusLog",
        version=__version__,
        db_path=str(Path(request.app.state.db_path)),
        platform=platform.platform(),
    )

