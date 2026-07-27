from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.sessions import session_repository
from app.domain.stage_report import build_stage_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/stage")
def stage_report(
    user_id: str = Query(default="owner", min_length=1, max_length=120),
    limit: int = Query(default=500, ge=1, le=1000),
) -> dict:
    sessions = session_repository().list_recent(user_id=user_id, limit=limit)
    return build_stage_report(sessions)
