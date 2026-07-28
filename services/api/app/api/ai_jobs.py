from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.ai_teacher import AiTeacherChatRequest, chat_with_ai_teacher
from app.api.sessions import session_repository
from app.repositories.ai_job_repository import AiJobRepository
from app.services.ai_teacher import ai_provider_public_status

router = APIRouter(prefix="/ai-jobs", tags=["ai-jobs"])


class DurableAiJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    session_id: str = Field(min_length=1, max_length=120)
    question_ids: list[str] = Field(default_factory=list, max_length=40)
    idempotency_key: str = Field(min_length=8, max_length=240)


class DurableAiJobAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)


def repository() -> AiJobRepository:
    return AiJobRepository(session_repository().database_path)


def _wrong_questions(user_id: str, session_id: str) -> list[dict[str, Any]]:
    stored = session_repository().get(user_id=user_id, session_id=session_id)
    if not stored:
        raise HTTPException(status_code=404, detail="Submitted session not found")
    return [
        row
        for row in (stored.result.get("question_results") or [])
        if not bool(row.get("is_correct")) and str(row.get("id") or "").strip()
    ]


@router.post("")
def create_durable_ai_job(payload: DurableAiJobCreate) -> dict[str, Any]:
    wrong = _wrong_questions(payload.user_id, payload.session_id)
    by_id = {str(row["id"]): row for row in wrong}
    requested_ids = list(dict.fromkeys(payload.question_ids)) or list(by_id)
    unknown = sorted(set(requested_ids) - set(by_id))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "wrong_question_required",
                "message": "逐题任务只能包含该已交卷 Session 中的错题。",
                "question_ids": unknown,
            },
        )
    if not requested_ids:
        raise HTTPException(
            status_code=400,
            detail={"code": "no_wrong_questions", "message": "这个 Session 没有可处理的错题。"},
        )
    provider = ai_provider_public_status()
    try:
        return repository().create_or_get(
            user_id=payload.user_id,
            session_id=payload.session_id,
            idempotency_key=payload.idempotency_key,
            provider=str(provider["selected"]),
            model=str(provider["model"]),
            questions=[by_id[question_id] for question_id in requested_ids],
        )
    except ValueError as error:
        if str(error) == "idempotency_key_conflict":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "idempotency_key_conflict",
                    "message": "相同任务键已用于不同 Session 或题目集合，请刷新后重试。",
                },
            ) from error
        raise


@router.get("")
def list_durable_ai_jobs(
    user_id: str = Query(default="owner", min_length=1, max_length=120),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    items = repository().list_jobs(user_id, limit=limit)
    return {"count": len(items), "items": items}


@router.get("/{job_id}")
def get_durable_ai_job(
    job_id: str,
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> dict[str, Any]:
    job = repository().get_job(user_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Durable AI job not found")
    return job


@router.post("/{job_id}/resume")
def resume_durable_ai_job(
    job_id: str,
    payload: DurableAiJobAction,
) -> dict[str, Any]:
    store = repository()
    job = store.get_job(payload.user_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Durable AI job not found")
    provider = ai_provider_public_status()
    if not provider.get("configured"):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ai_not_configured",
                "message": "当前 AI 老师未配置密钥；任务仍保留，配置后可继续。",
            },
        )
    claimed = store.claim_next(user_id=payload.user_id, job_id=job_id)
    if not claimed:
        return store.get_job(payload.user_id, job_id) or job
    try:
        response = chat_with_ai_teacher(AiTeacherChatRequest(
            user_id=payload.user_id,
            context_type="wrong_question",
            session_id=job["session_id"],
            question_id=claimed["question_id"],
            question=(
                "请基于服务端提供的标准答案、题库解析、核验证据和我的错因确认，"
                "逐步解释这道题为什么错、题干与原文如何对应，并给出下一次可执行的检查步骤。"
            ),
        ))
    except HTTPException as error:
        detail = error.detail if isinstance(error.detail, dict) else {}
        code = str(detail.get("code") or "")
        store.fail(
            user_id=payload.user_id,
            job_id=job_id,
            item_id=claimed["id"],
            worker_token=claimed["worker_token"],
            message=str(detail.get("message") or error.detail),
            retryable=code in {"ai_provider_failed", "ai_daily_limit_reached"},
        )
        raise
    except Exception as error:
        store.fail(
            user_id=payload.user_id,
            job_id=job_id,
            item_id=claimed["id"],
            worker_token=claimed["worker_token"],
            message="AI 逐题任务处理失败，已保留重试状态。",
            retryable=True,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "code": "ai_job_processing_failed",
                "message": "AI 逐题任务处理失败，任务已保留，可稍后继续。",
            },
        ) from error
    completed = store.complete(
        user_id=payload.user_id,
        job_id=job_id,
        item_id=claimed["id"],
        worker_token=claimed["worker_token"],
        result={
            "answer": response.get("answer"),
            "cached": bool(response.get("cached")),
            "provider": response.get("provider"),
            "model": response.get("model"),
            "conversation_id": (response.get("conversation") or {}).get("id"),
        },
    )
    if not completed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ai_job_lease_lost",
                "message": "任务租约已失效，结果未写入；请刷新任务状态。",
            },
        )
    return store.get_job(payload.user_id, job_id) or job
