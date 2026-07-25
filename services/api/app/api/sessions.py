from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.question_bank import question_bank
from app.domain.scoring import score_submission
from app.repositories.session_repository import SQLiteSessionRepository, StoredSession
from app.services.question_bank import QuestionBankNotReadyError

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    test_id: str = Field(min_length=1, max_length=120)
    client_submission_id: str = Field(min_length=8, max_length=160)
    answers: dict[str, str | list[str]] = Field(default_factory=dict)
    elapsed_seconds: int = Field(default=0, ge=0, le=21600)
    exam_mode: Literal["study", "part_practice", "mock_exam"] = "mock_exam"
    part_numbers: list[int] = Field(default_factory=list, max_length=3)
    timed_out: bool = False


class SessionSummary(BaseModel):
    session_id: str
    test_id: str
    test_title: str
    created_at: str
    score: int
    total: int
    accuracy: float
    estimated_band: float | None = None
    exam_mode: str
    part_numbers: list[int]


class SessionEnvelope(BaseModel):
    session_id: str
    created_at: str
    idempotent_replay: bool
    result: dict[str, Any]


def session_repository() -> SQLiteSessionRepository:
    path = Path(
        os.getenv(
            "SESSION_DB_PATH",
            str(Path(__file__).resolve().parents[2] / "data" / "sessions.sqlite3"),
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return SQLiteSessionRepository(path)


def _envelope(stored: StoredSession) -> SessionEnvelope:
    return SessionEnvelope(
        session_id=stored.id,
        created_at=stored.created_at,
        idempotent_replay=stored.idempotent_replay,
        result=stored.result,
    )


def _select_parts(test: dict[str, Any], part_numbers: list[int]) -> tuple[dict[str, Any], list[int]]:
    available = [int(part.get("number") or 0) for part in test.get("parts") or []]
    if not part_numbers:
        selected = available
    else:
        selected = list(dict.fromkeys(int(number) for number in part_numbers))
        invalid = [number for number in selected if number not in available]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_part_numbers", "invalid": invalid},
            )
    selected_set = set(selected)
    filtered = {
        **test,
        "parts": [
            part for part in test.get("parts") or []
            if int(part.get("number") or 0) in selected_set
        ],
        "practice_mode": "full_test" if selected == available else "part_practice",
    }
    return filtered, selected


@router.post("/submit", response_model=SessionEnvelope)
def submit_session(payload: SessionSubmitRequest) -> SessionEnvelope:
    repository = session_repository()
    existing = repository.get_by_client_submission_id(
        payload.user_id, payload.client_submission_id
    )
    if existing:
        return _envelope(existing)

    try:
        authoritative_test = question_bank().load_server_test(payload.test_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Test not found") from error
    except QuestionBankNotReadyError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "question_bank_migration_incomplete", "message": str(error)},
        ) from error

    scored_test, selected_parts = _select_parts(authoritative_test, payload.part_numbers)
    result = score_submission(
        scored_test,
        payload.answers,
        exam_mode=payload.exam_mode,
        total_elapsed_seconds=payload.elapsed_seconds,
    )
    result["part_numbers"] = selected_parts
    result["timed_out"] = payload.timed_out
    stored = repository.save_or_get(
        user_id=payload.user_id,
        client_submission_id=payload.client_submission_id,
        test_id=payload.test_id,
        result=result,
    )
    return _envelope(stored)


@router.get("", response_model=list[SessionSummary])
def list_sessions(
    user_id: str = Query(default="owner", min_length=1, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[SessionSummary]:
    rows = session_repository().list_recent(user_id=user_id, limit=limit)
    return [
        SessionSummary(
            session_id=row.id,
            test_id=row.test_id,
            test_title=str(row.result.get("test_title") or row.test_id),
            created_at=row.created_at,
            score=int(row.result.get("score") or 0),
            total=int(row.result.get("total") or 0),
            accuracy=float(row.result.get("accuracy") or 0),
            estimated_band=row.result.get("estimated_gt_reading_band"),
            exam_mode=str(row.result.get("exam_mode") or "study"),
            part_numbers=[int(number) for number in (row.result.get("part_numbers") or [])],
        )
        for row in rows
    ]


@router.get("/{session_id}", response_model=SessionEnvelope)
def get_session(
    session_id: str,
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> SessionEnvelope:
    stored = session_repository().get(user_id=user_id, session_id=session_id)
    if not stored:
        raise HTTPException(status_code=404, detail="Session not found")
    return _envelope(stored)
