from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.sessions import session_repository
from app.services.ai_teacher import (
    AiTeacherNotConfiguredError,
    ai_provider_public_status,
    select_ai_provider,
)

router = APIRouter(prefix="/ai-teacher", tags=["ai-teacher"])
PROVIDER_SETTING_KEY = "ai_provider"


class ProviderSelectionRequest(BaseModel):
    provider: Literal["qwen", "deepseek", "openai"]


def _restore_saved_provider() -> None:
    saved = session_repository().get_setting(PROVIDER_SETTING_KEY)
    if saved:
        select_ai_provider(saved)


@router.get("/provider")
def get_ai_provider() -> dict[str, Any]:
    try:
        _restore_saved_provider()
        return ai_provider_public_status()
    except AiTeacherNotConfiguredError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "ai_not_configured", "message": str(error)},
        ) from error


@router.put("/provider")
def update_ai_provider(payload: ProviderSelectionRequest) -> dict[str, Any]:
    try:
        selected = select_ai_provider(payload.provider)
        session_repository().set_setting(PROVIDER_SETTING_KEY, selected)
        return ai_provider_public_status()
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
