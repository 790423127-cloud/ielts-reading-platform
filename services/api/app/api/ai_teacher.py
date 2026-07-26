from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.sentence_training import sentence_repository, sentence_training_bank
from app.api.sessions import session_repository
from app.repositories.ai_teacher_repository import AiTeacherRepository
from app.repositories.learning_plan_repository import LearningPlanRepository
from app.services.ai_teacher import (
    AiTeacherNotConfiguredError,
    AiTeacherProviderError,
    ai_provider_cache_identity,
    generate_ai_reply,
)

router = APIRouter(prefix="/ai-teacher", tags=["ai-teacher"])


class AiTeacherChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    context_type: Literal["wrong_question", "sentence", "plan"]
    question: str = Field(min_length=2, max_length=3000)
    session_id: str | None = Field(default=None, max_length=120)
    question_id: str | None = Field(default=None, max_length=180)
    sentence_id: str | None = Field(default=None, max_length=120)


def ai_repository() -> AiTeacherRepository:
    return AiTeacherRepository(session_repository().database_path)


def _wrong_question_context(payload: AiTeacherChatRequest) -> tuple[str, str, dict[str, Any]]:
    if not payload.session_id or not payload.question_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "wrong_question_reference_required", "message": "错题提问必须绑定已交卷Session和题目。"},
        )
    stored = session_repository().get(user_id=payload.user_id, session_id=payload.session_id)
    if not stored:
        raise HTTPException(status_code=404, detail="Submitted session not found")
    question = next(
        (
            row
            for row in (stored.result.get("question_results") or [])
            if str(row.get("id") or "") == payload.question_id
        ),
        None,
    )
    if not question:
        raise HTTPException(status_code=404, detail="Question not found in submitted session")
    if bool(question.get("is_correct")):
        raise HTTPException(
            status_code=400,
            detail={"code": "wrong_question_required", "message": "这个入口只解释已交卷错题。"},
        )
    context_ref = f"{stored.id}:{payload.question_id}"
    title = f"错题 Q{question.get('number') or payload.question_id}"
    context = {
        "source": "submitted_session",
        "session_id": stored.id,
        "test_id": stored.result.get("test_id"),
        "test_title": stored.result.get("test_title"),
        "exam_mode": stored.result.get("exam_mode"),
        "submitted_at": stored.created_at,
        "question": {
            "id": question.get("id"),
            "number": question.get("number"),
            "part_number": question.get("part_number"),
            "question_type": question.get("question_type"),
            "question_subtype": question.get("question_subtype"),
            "prompt": question.get("prompt"),
            "user_answer": question.get("user_answer"),
            "correct_answer": question.get("correct_answer"),
            "answer_error_type": question.get("answer_error_type"),
            "analysis": question.get("analysis") or question.get("reason"),
            "paraphrasing": question.get("paraphrasing"),
            "evidence": question.get("evidence") or [],
        },
        "policy": {
            "answer_is_server_authoritative": True,
            "ai_can_change_answer_or_score": False,
            "unverified_evidence_must_not_be_invented": True,
        },
    }
    return context_ref, title, context


def _sentence_context(payload: AiTeacherChatRequest) -> tuple[str, str, dict[str, Any]]:
    if not payload.sentence_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "sentence_reference_required", "message": "长难句提问必须绑定已保存句子。"},
        )
    item = sentence_repository().get_sentence(user_id=payload.user_id, sentence_id=payload.sentence_id)
    if not item:
        raise HTTPException(status_code=404, detail="Personal sentence not found")
    if item.get("permission") == "locked":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ai_locked_until_submission",
                "message": "这条句子来源尚未交卷，AI老师不能提前分析。",
            },
        )
    standard_parse = None
    if item.get("permission") == "verified" and item.get("verified_item_id"):
        verified = sentence_training_bank().get(str(item["verified_item_id"]))
        standard_parse = {
            "roles": verified.get("roles") or {},
            "logic": verified.get("logic"),
            "explanation": verified.get("explanation"),
            "simplified_zh": verified.get("simplified_zh"),
            "answer_impact": verified.get("answer_impact"),
            "status": "reviewed_standard",
        }
    context = {
        "source": "personal_sentence",
        "sentence_id": item["id"],
        "sentence": item["sentence"],
        "previous_sentence": item.get("previous_sentence"),
        "next_sentence": item.get("next_sentence"),
        "paragraph": item.get("paragraph"),
        "source_type": item.get("source_type"),
        "test_title": item.get("test_title"),
        "part_number": item.get("part_number"),
        "learner_analysis": item.get("analysis") or {},
        "standard_parse": standard_parse,
        "policy": {
            "verified_standard_available": standard_parse is not None,
            "unreviewed_analysis_is_not_standard": standard_parse is None,
            "ai_can_change_saved_analysis": False,
        },
    }
    return str(item["id"]), f"长难句：{str(item['sentence'])[:42]}", context


def _plan_context(payload: AiTeacherChatRequest) -> tuple[str, str, dict[str, Any]]:
    sessions_repo = session_repository()
    sessions = sessions_repo.list_recent(user_id=payload.user_id, limit=100)
    plan = LearningPlanRepository(sessions_repo.database_path).synchronize(
        user_id=payload.user_id,
        sessions=sessions,
    )
    context = {
        "source": "server_learning_plan",
        "policy": plan.get("policy"),
        "active_task_count": plan.get("active_task_count"),
        "mastered_skill_count": plan.get("mastered_skill_count"),
        "due_review_count": plan.get("due_review_count"),
        "tasks": (plan.get("tasks") or [])[:12],
        "skill_mastery": plan.get("skill_mastery") or [],
        "due_reviews": plan.get("due_reviews") or [],
        "ai_permissions": {
            "can_explain": True,
            "can_mark_mastery": False,
            "can_change_task_status": False,
        },
    }
    return "current", "当前学习计划", context


def _resolve_context(payload: AiTeacherChatRequest) -> tuple[str, str, dict[str, Any]]:
    if payload.context_type == "wrong_question":
        return _wrong_question_context(payload)
    if payload.context_type == "sentence":
        return _sentence_context(payload)
    return _plan_context(payload)


def _stable_context(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _stable_context(item)
            for key, item in value.items()
            if key not in {"created_at", "updated_at"}
        }
    if isinstance(value, list):
        return [_stable_context(item) for item in value]
    return value


def _context_cache_ref(context_ref: str, context: dict[str, Any]) -> str:
    serialized = json.dumps(
        _stable_context(context),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"{context_ref}:{digest}"


def _daily_limit() -> int:
    try:
        return max(1, min(int(os.getenv("AI_DAILY_REQUEST_LIMIT", "30")), 500))
    except ValueError:
        return 30


def _provider_identity() -> str:
    try:
        return ai_provider_cache_identity()
    except AiTeacherNotConfiguredError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "ai_not_configured", "message": str(error)},
        ) from error


@router.post("/chat")
def chat_with_ai_teacher(payload: AiTeacherChatRequest) -> dict[str, Any]:
    context_ref, title, context = _resolve_context(payload)
    repository = ai_repository()
    conversation = repository.get_or_create_conversation(
        user_id=payload.user_id,
        context_type=payload.context_type,
        context_ref=context_ref,
        title=title,
    )
    question = " ".join(payload.question.strip().split())
    provider_identity = _provider_identity()
    cache_key = repository.cache_key(
        user_id=payload.user_id,
        context_type=payload.context_type,
        context_ref=f"{_context_cache_ref(context_ref, context)}:{provider_identity}",
        question=question,
    )
    cached = repository.get_cached(cache_key=cache_key, user_id=payload.user_id)

    if cached:
        repository.append_message(
            conversation_id=conversation["id"],
            role="user",
            content=question,
        )
        updated = repository.append_message(
            conversation_id=conversation["id"],
            role="assistant",
            content=cached["answer"],
            model=cached.get("model"),
            input_tokens=0,
            output_tokens=0,
            cached=True,
            provider_request_id=cached.get("provider_request_id"),
        )
        return {
            "answer": cached["answer"],
            "cached": True,
            "model": cached.get("model"),
            "conversation": updated,
            "policy": {
                "can_change_answer_or_score": False,
                "can_mark_mastery": False,
                "daily_provider_limit": _daily_limit(),
            },
        }

    calls_today = repository.provider_calls_today(user_id=payload.user_id)
    limit = _daily_limit()
    if calls_today >= limit:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "ai_daily_limit_reached",
                "message": f"今天已达到 {limit} 次AI调用上限，缓存回答仍可继续查看。",
            },
        )

    history = [
        {"role": message["role"], "content": message["content"]}
        for message in conversation.get("messages") or []
    ]
    try:
        generated = generate_ai_reply(
            question=question,
            context_type=payload.context_type,
            context=context,
            history=history,
        )
    except AiTeacherNotConfiguredError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "ai_not_configured", "message": str(error)},
        ) from error
    except AiTeacherProviderError as error:
        raise HTTPException(
            status_code=502,
            detail={"code": "ai_provider_failed", "message": str(error)},
        ) from error

    repository.save_cache(
        cache_key=cache_key,
        user_id=payload.user_id,
        context_type=payload.context_type,
        context_ref=context_ref,
        question=question,
        answer=generated["answer"],
        model=generated.get("model"),
        input_tokens=int(generated.get("input_tokens") or 0),
        output_tokens=int(generated.get("output_tokens") or 0),
        provider_request_id=generated.get("provider_request_id"),
    )
    repository.append_message(
        conversation_id=conversation["id"],
        role="user",
        content=question,
    )
    updated = repository.append_message(
        conversation_id=conversation["id"],
        role="assistant",
        content=generated["answer"],
        model=generated.get("model"),
        input_tokens=int(generated.get("input_tokens") or 0),
        output_tokens=int(generated.get("output_tokens") or 0),
        cached=False,
        provider_request_id=generated.get("provider_request_id"),
    )
    return {
        "answer": generated["answer"],
        "cached": False,
        "provider": generated.get("provider"),
        "model": generated.get("model"),
        "conversation": updated,
        "policy": {
            "can_change_answer_or_score": False,
            "can_mark_mastery": False,
            "daily_provider_limit": limit,
            "provider_calls_today": calls_today + 1,
        },
    }


@router.get("/conversations")
def list_ai_conversations(
    user_id: str = Query(default="owner", min_length=1, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    repository = ai_repository()
    items = repository.list_conversations(user_id=user_id, limit=limit)
    return {
        "count": len(items),
        "items": items,
        "provider_calls_today": repository.provider_calls_today(user_id=user_id),
        "daily_provider_limit": _daily_limit(),
    }


@router.get("/conversations/{conversation_id}")
def get_ai_conversation(
    conversation_id: str,
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> dict[str, Any]:
    item = ai_repository().get_conversation(user_id=user_id, conversation_id=conversation_id)
    if not item:
        raise HTTPException(status_code=404, detail="AI conversation not found")
    return item


@router.delete("/conversations/{conversation_id}")
def delete_ai_conversation(
    conversation_id: str,
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> dict[str, bool]:
    deleted = ai_repository().delete_conversation(user_id=user_id, conversation_id=conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="AI conversation not found")
    return {"deleted": True}
