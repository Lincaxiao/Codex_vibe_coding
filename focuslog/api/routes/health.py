from __future__ import annotations

from fastapi import APIRouter

from ..schemas import HealthOut

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut()

