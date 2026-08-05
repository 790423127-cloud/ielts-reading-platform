from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.sessions import session_repository
from app.domain.review import build_wrong_question_review
from app.repositories.review_feedback_repository import ReviewFeedbackRepository

router = APIRouter(prefix="/review", tags=["review"])

CAUSE_OPTIONS = {
    "unknown_vocabulary": "不认识关键词",
    "paraphrase_failure": "没识别同义替换",
    "sentence_structure": "句子结构没看懂",
    "false_vs_not_given": "FALSE/NO 与 NOT GIVEN 混淆",
    "true_vs_not_given": "TRUE/YES 与 NOT GIVEN 混淆",
    "unsupported_inference": "做了原文不支持的推断",
    "scope_expansion": "把部分扩大成全部",
    "keyword_distractor": "被相同关键词干扰",
    "word_limit_exceeded": "超过词数限制",
    "spelling_error": "拼写错误",
    "singular_plural_error": "单复数错误",
    "instruction_misread": "看错题目要求",
    "location_failure": "没有正确定位",
    "time_pressure": "时间不够",
    "other": "其他原因",
}


class WrongQuestionFeedbackPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    match_status: Literal["matches", "partial", "does_not_match"]
    understanding_status: Literal["understood", "needs_review"]
    cause_id: str | None = Field(default=None, max_length=80)
    note: str = Field(default="", max_length=2000)


def feedback_repository() -> ReviewFeedbackRepository:
    return ReviewFeedbackRepository(session_repository().database_path)


@router.get("/wrong-questions")
def wrong_questions(
    user_id: str = Query(default="owner", min_length=1, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    sessions = session_repository().list_recent(user_id=user_id, limit=limit)
    items = build_wrong_question_review(sessions)
    feedback = feedback_repository().list_for_user(user_id)
    for item in items:
        item["student_feedback"] = feedback.get(
            (str(item["source_session_id"]), str(item["id"]))
        )
    return {
        "count": len(items),
        "items": items,
        "mastery_rule": "最近一次错误后连续答对2次才移出错题库",
        "cause_options": [
            {"id": cause_id, "label": label}
            for cause_id, label in CAUSE_OPTIONS.items()
        ],
    }


@router.post("/wrong-questions/{session_id}/{question_id}/feedback")
def save_wrong_question_feedback(
    session_id: str,
    question_id: str,
    payload: WrongQuestionFeedbackPayload,
) -> dict:
    stored = session_repository().get(
        user_id=payload.user_id,
        session_id=session_id,
    )
    if not stored:
        raise HTTPException(status_code=404, detail="Submitted session not found")
    question = next(
        (
            item
            for item in (stored.result.get("question_results") or [])
            if str(item.get("id") or "") == question_id
        ),
        None,
    )
    if not question or bool(question.get("is_correct")):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "wrong_question_required",
                "message": "只能为当前已交卷Session中的错题确认原因。",
            },
        )
    cause_id = (payload.cause_id or "").strip() or None
    if cause_id and cause_id not in CAUSE_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail={"code": "unknown_cause", "message": "请选择系统提供的错因。"},
        )
    return feedback_repository().save(
        user_id=payload.user_id,
        session_id=session_id,
        question_id=question_id,
        match_status=payload.match_status,
        understanding_status=payload.understanding_status,
        cause_id=cause_id,
        note=payload.note.strip(),
    )
