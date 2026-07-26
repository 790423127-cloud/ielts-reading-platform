from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.ai_teacher import (
    AiTeacherNotConfiguredError,
    ai_provider_public_status,
)

router = APIRouter(prefix="/ai-teacher", tags=["ai-teacher"])


@router.get("/provider")
def get_ai_provider() -> dict[str, Any]:
    try:
        return ai_provider_public_status()
    except AiTeacherNotConfiguredError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "ai_not_configured", "message": str(error)},
        ) from error
