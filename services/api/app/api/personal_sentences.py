from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.sentence_training import sentence_repository, sentence_training_bank
from app.api.sessions import session_repository
from app.services.sentence_training import STEP_KEYS, normalize_span

router = APIRouter(prefix="/sentences", tags=["personal-sentences"])

SOURCE_TYPES = {"reading_selection", "wrong_evidence", "mock_mark", "manual"}
ANALYSIS_KEYS = set(STEP_KEYS) | {"note"}


class SentenceCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    sentence: str = Field(min_length=3, max_length=4000)
    previous_sentence: str | None = Field(default=None, max_length=4000)
    next_sentence: str | None = Field(default=None, max_length=4000)
    paragraph: str | None = Field(default=None, max_length=12000)
    source_type: Literal["reading_selection", "wrong_evidence", "mock_mark", "manual"] = "manual"
    source_session_id: str | None = Field(default=None, max_length=120)
    source_question_id: str | None = Field(default=None, max_length=180)
    test_id: str | None = Field(default=None, max_length=120)
    test_title: str | None = Field(default=None, max_length=300)
    part_number: int | None = Field(default=None, ge=1, le=99)
    paragraph_index: int | None = Field(default=None, ge=0, le=999)
    exam_mode: str | None = Field(default=None, max_length=80)


class SentenceAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    predicate: str = Field(default="", max_length=4000)
    subject: str = Field(default="", max_length=4000)
    object: str = Field(default="", max_length=4000)
    scope: str = Field(default="", max_length=4000)
    logic: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=8000)


def _find_session_question(
    session_result: dict[str, Any],
    *,
    question_id: str | None,
) -> dict[str, Any] | None:
    rows = session_result.get("question_results") or []
    if question_id:
        return next(
            (row for row in rows if str(row.get("id") or "") == question_id),
            None,
        )
    return None


def _sentence_in_evidence(sentence: str, question: dict[str, Any] | None) -> bool:
    if not question:
        return False
    target = normalize_span(sentence)
    return any(normalize_span(value) == target for value in (question.get("evidence") or []))


def _resolve_permission(payload: SentenceCaptureRequest) -> tuple[str, str | None]:
    if payload.source_type == "manual":
        return "self_only", None

    submitted_session = None
    if payload.source_session_id:
        submitted_session = session_repository().get(
            user_id=payload.user_id,
            session_id=payload.source_session_id,
        )

    if payload.source_type == "wrong_evidence":
        if not submitted_session:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "submitted_session_required",
                    "message": "错题证据句必须来自已交卷Session。",
                },
            )
        question = _find_session_question(
            submitted_session.result,
            question_id=payload.source_question_id,
        )
        if not question or bool(question.get("is_correct")):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "wrong_question_required",
                    "message": "错题证据句必须绑定该Session中的错题。",
                },
            )
        if not _sentence_in_evidence(payload.sentence, question):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "evidence_sentence_mismatch",
                    "message": "句子与题库核验定位句不一致。",
                },
            )
    elif not submitted_session:
        # Active mock/study selection can be collected, but no analysis or standard
        # parse is unlocked until a submitted session exists.
        return "locked", None

    verified = sentence_training_bank().find_exact_sentence(payload.sentence)
    if verified and submitted_session:
        return "verified", str(verified["id"])
    return "self_only", None


def _enrich(item: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(item)
    verified_item_id = item.get("verified_item_id")
    if item.get("permission") == "verified" and verified_item_id:
        verified = sentence_training_bank().get(str(verified_item_id))
        roles = verified.get("roles") or {}
        enriched["standard_parse"] = {
            "predicate": str(roles.get("predicate") or ""),
            "subject": str(roles.get("subject") or ""),
            "object": str(roles.get("object") or ""),
            "scope": str(roles.get("scope") or ""),
            "logic": str(verified.get("logic") or "none"),
            "explanation": str(verified.get("explanation") or ""),
            "simplified_zh": str(verified.get("simplified_zh") or ""),
            "answer_impact": str(verified.get("answer_impact") or ""),
        }
        enriched["standard_parse_label"] = "审核标准拆解"
    else:
        enriched["standard_parse"] = None
        enriched["standard_parse_label"] = None
    enriched["analysis_allowed"] = item.get("permission") != "locked"
    enriched["ai_analysis_available"] = False
    return enriched


@router.get("")
def list_personal_sentences(
    user_id: str = Query(default="owner", min_length=1, max_length=120),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    items = sentence_repository().list_sentences(user_id=user_id, limit=limit)
    return {
        "count": len(items),
        "items": [_enrich(item) for item in items],
        "analysis_keys": [*STEP_KEYS, "note"],
        "unverified_standard_parse": False,
        "ai_calls": 0,
    }


@router.post("")
def capture_personal_sentence(payload: SentenceCaptureRequest) -> dict[str, Any]:
    permission, verified_item_id = _resolve_permission(payload)
    item = sentence_repository().capture_sentence(
        user_id=payload.user_id,
        payload=payload.model_dump(),
        permission=permission,
        verified_item_id=verified_item_id,
    )
    return _enrich(item)


@router.put("/{sentence_id}/analysis")
def update_personal_sentence_analysis(
    sentence_id: str,
    payload: SentenceAnalysisRequest,
) -> dict[str, Any]:
    repository = sentence_repository()
    current = repository.get_sentence(user_id=payload.user_id, sentence_id=sentence_id)
    if not current:
        raise HTTPException(status_code=404, detail="Personal sentence not found")
    if current.get("permission") == "locked":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "analysis_locked_until_submission",
                "message": "当前来源尚未交卷，只能保存标记，不能分析。",
            },
        )
    analysis = {
        key: str(value or "")
        for key, value in payload.model_dump(exclude={"user_id"}).items()
        if key in ANALYSIS_KEYS
    }
    updated = repository.update_analysis(
        user_id=payload.user_id,
        sentence_id=sentence_id,
        analysis=analysis,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Personal sentence not found")
    return _enrich(updated)


@router.delete("/{sentence_id}")
def delete_personal_sentence(
    sentence_id: str,
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> dict[str, bool]:
    deleted = sentence_repository().delete_sentence(user_id=user_id, sentence_id=sentence_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Personal sentence not found")
    return {"deleted": True}
