from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.question_bank import question_bank
from app.api.sessions import SessionEnvelope, session_repository
from app.domain.ability_training import (
    QUESTION_TYPE_TARGETS,
    SKILL_BY_ID,
    TRAINING_TARGET_BY_ID,
    available_counts,
    build_authoritative_ability_test,
    generate_ability_set,
    question_type_catalog,
    skill_catalog,
)
from app.domain.scoring import score_submission
from app.services.question_bank import QuestionBankNotReadyError

router = APIRouter(prefix="/ability", tags=["ability"])
QuestionElapsedSeconds = Annotated[int, Field(ge=0, le=21600)]


class AbilityGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(min_length=1, max_length=80)
    count: int = Field(default=8, ge=1, le=20)
    cursor: int = Field(default=0, ge=0)
    question_refs: list[str] = Field(default_factory=list, max_length=20)


class AbilitySubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    client_submission_id: str = Field(min_length=8, max_length=160)
    skill_id: str = Field(min_length=1, max_length=80)
    question_refs: list[str] = Field(min_length=1, max_length=20)
    answers: dict[str, str | list[str]] = Field(default_factory=dict)
    elapsed_seconds: int = Field(default=0, ge=0, le=21600)
    question_elapsed_seconds: dict[str, QuestionElapsedSeconds] = Field(
        default_factory=dict, max_length=20
    )


@lru_cache(maxsize=1)
def _cached_counts() -> dict[str, int]:
    return available_counts(
        question_bank(),
        (*SKILL_BY_ID.values(), *QUESTION_TYPE_TARGETS),
    )


@router.get("/skills")
def list_skills() -> dict:
    try:
        counts = _cached_counts()
    except QuestionBankNotReadyError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "question_bank_migration_incomplete", "message": str(error)},
        ) from error
    items = [
        {**item, "available_questions": counts.get(str(item["id"]), 0)}
        for item in skill_catalog()
    ]
    question_types = [
        {**item, "available_questions": counts.get(str(item["id"]), 0)}
        for item in question_type_catalog()
    ]
    return {
        "items": items,
        "question_types": question_types,
        "count": len(items),
        "question_type_count": len(question_types),
        "source_policy": "verified_question_bank_only",
        "ai_calls": 0,
    }


@router.post("/generate")
def generate(payload: AbilityGenerateRequest) -> dict[str, Any]:
    if payload.skill_id not in TRAINING_TARGET_BY_ID:
        raise HTTPException(status_code=404, detail="Training target not found")
    try:
        return generate_ability_set(
            question_bank(),
            skill_id=payload.skill_id,
            count=payload.count,
            cursor=payload.cursor,
            question_refs=payload.question_refs,
        )
    except (KeyError, ValueError) as error:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_question_replay", "message": str(error)},
        ) from error
    except QuestionBankNotReadyError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "question_bank_migration_incomplete", "message": str(error)},
        ) from error


@router.post("/submit", response_model=SessionEnvelope)
def submit(payload: AbilitySubmitRequest) -> SessionEnvelope:
    if payload.skill_id not in TRAINING_TARGET_BY_ID:
        raise HTTPException(status_code=404, detail="Training target not found")
    repository = session_repository()
    existing = repository.get_by_client_submission_id(
        payload.user_id, payload.client_submission_id
    )
    if existing:
        return SessionEnvelope(
            session_id=existing.id,
            created_at=existing.created_at,
            idempotent_replay=True,
            result=existing.result,
        )
    try:
        test = build_authoritative_ability_test(
            question_bank(),
            skill_id=payload.skill_id,
            question_refs=payload.question_refs,
        )
    except (KeyError, ValueError, QuestionBankNotReadyError) as error:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_ability_set", "message": str(error)},
        ) from error

    allowed_refs = set(payload.question_refs)
    unexpected_answers = sorted(set(payload.answers) - allowed_refs)
    if unexpected_answers:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unexpected_answer_keys",
                "question_refs": unexpected_answers,
            },
        )
    unexpected_timing_keys = sorted(
        set(payload.question_elapsed_seconds) - allowed_refs
    )
    if unexpected_timing_keys:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unexpected_question_timing_keys",
                "question_refs": unexpected_timing_keys,
            },
        )
    result = score_submission(
        test,
        payload.answers,
        exam_mode="ability",
        total_elapsed_seconds=payload.elapsed_seconds,
        question_elapsed_seconds=payload.question_elapsed_seconds,
    )
    result["part_numbers"] = [
        int(row.get("part_number") or 0) for row in result.get("part_results") or []
    ]
    result["skill_id"] = payload.skill_id
    result["skill_label"] = TRAINING_TARGET_BY_ID[payload.skill_id].label
    result["source_question_refs"] = list(payload.question_refs)
    result["source_policy"] = "verified_question_bank_only"
    result["training_kind"] = (
        "wrong_batch"
        if payload.skill_id == "wrong-batch"
        else "question_type" if payload.skill_id.startswith("subtype-") else "ability"
    )
    stored = repository.save_or_get(
        user_id=payload.user_id,
        client_submission_id=payload.client_submission_id,
        test_id=f"ability-{payload.skill_id}",
        result=result,
    )
    return SessionEnvelope(
        session_id=stored.id,
        created_at=stored.created_at,
        idempotent_replay=stored.idempotent_replay,
        result=stored.result,
    )
