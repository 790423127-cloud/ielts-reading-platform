from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.api.question_bank import question_bank
from app.domain.scoring import score_submission
from app.repositories.vocabulary_repository import VocabularyRepository
from app.repositories.session_repository import SQLiteSessionRepository, StoredSession
from app.services.question_bank import QuestionBankNotReadyError
from app.services.paraphrase_extractor import extract_wrong_question_paraphrases

router = APIRouter(prefix="/sessions", tags=["sessions"])
QuestionElapsedSeconds = Annotated[int, Field(ge=0, le=21600)]
PartElapsedSeconds = Annotated[int, Field(ge=0, le=21600)]


class SessionAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(min_length=1, max_length=160)
    kind: Literal["highlight", "note"]
    highlight_level: Literal["primary", "secondary"] = Field(
        default="primary",
        alias="highlightLevel",
    )
    test_id: str = Field(alias="testId", min_length=1, max_length=120)
    test_title: str = Field(alias="testTitle", min_length=1, max_length=300)
    part_number: int = Field(alias="partNumber", ge=1, le=3)
    paragraph_index: int = Field(alias="paragraphIndex", ge=0, le=500)
    start_offset: int = Field(alias="startOffset", ge=0, le=200000)
    end_offset: int = Field(alias="endOffset", ge=1, le=200000)
    selected_text: str = Field(alias="selectedText", min_length=1, max_length=300)
    prefix: str = Field(default="", max_length=500)
    suffix: str = Field(default="", max_length=500)
    sentence: str = Field(default="", max_length=5000)
    note: str = Field(default="", max_length=5000)
    created_at: str = Field(alias="createdAt", min_length=1, max_length=80)
    updated_at: str = Field(alias="updatedAt", min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_offsets_and_note(self) -> "SessionAnnotation":
        if self.end_offset <= self.start_offset:
            raise ValueError("annotation endOffset must be greater than startOffset")
        if self.kind == "note" and not self.note.strip():
            raise ValueError("note annotations require note text")
        return self


class SessionSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    test_id: str = Field(min_length=1, max_length=120)
    client_submission_id: str = Field(min_length=8, max_length=160)
    answers: dict[str, str | list[str]] = Field(default_factory=dict)
    elapsed_seconds: int = Field(default=0, ge=0, le=21600)
    part_elapsed_seconds: dict[str, PartElapsedSeconds] = Field(
        default_factory=dict,
        alias="partElapsedSeconds",
    )
    question_elapsed_seconds: dict[str, QuestionElapsedSeconds] = Field(
        default_factory=dict,
        alias="questionElapsedSeconds",
    )
    exam_mode: Literal["study", "part_practice", "mock_exam"] = "mock_exam"
    part_numbers: list[int] = Field(default_factory=list, max_length=3)
    timed_out: bool = False
    # 标注、笔记属于附加学习数据，旧浏览器草稿可能保留早期结构。
    # 先接收原始值，再在已确认试卷和 Part 后逐条校验，不能让一条旧标注阻断整卷判分。
    annotations: list[Any] = Field(default_factory=list, max_length=500)


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
    archived: bool = False


class SessionEnvelope(BaseModel):
    session_id: str
    created_at: str
    idempotent_replay: bool
    result: dict[str, Any]


class SessionDeleteBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    session_ids: list[str] = Field(min_length=1, max_length=100)


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


def _extract_and_persist_paraphrases(
    *,
    database_path: str,
    user_id: str,
    session_id: str,
    scored_result: dict[str, Any],
) -> None:
    session_store = SQLiteSessionRepository(database_path)
    try:
        summary = extract_wrong_question_paraphrases(
            repository=VocabularyRepository(database_path),
            user_id=user_id,
            session_id=session_id,
            result=scored_result,
        )
    except Exception:
        summary = {
            "status": "failed",
            "reason": "unexpected_extraction_error",
            "wrong_question_count": len(scored_result.get("wrong_questions") or []),
            "candidate_count": 0,
            "saved_count": 0,
        }
    stored = session_store.get(user_id=user_id, session_id=session_id)
    if not stored:
        return
    next_result = dict(stored.result)
    next_result["ai_paraphrase_summary"] = summary
    session_store.update_result(
        user_id=user_id,
        session_id=session_id,
        result=next_result,
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


def _validated_annotations(
    payload: SessionSubmitRequest,
    *,
    selected_parts: list[int],
    authoritative_test: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = set(selected_parts)
    test_title = str(authoritative_test.get("title") or payload.test_id)
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_annotation in enumerate(payload.annotations):
        try:
            annotation = SessionAnnotation.model_validate(raw_annotation)
        except ValidationError:
            warnings.append({"index": index, "code": "invalid_annotation_ignored"})
            continue
        if annotation.id in seen:
            warnings.append({
                "index": index,
                "code": "duplicate_annotation_ignored",
                "annotation_id": annotation.id,
            })
            continue
        seen.add(annotation.id)
        if annotation.test_id != payload.test_id:
            warnings.append({
                "index": index,
                "code": "annotation_test_mismatch_ignored",
                "annotation_id": annotation.id,
            })
            continue
        if annotation.part_number not in selected:
            warnings.append({
                "index": index,
                "code": "annotation_part_not_submitted_ignored",
                "annotation_id": annotation.id,
            })
            continue
        row = annotation.model_dump(by_alias=True)
        row["testTitle"] = test_title
        rows.append(row)
    return rows, warnings


@router.post("/submit", response_model=SessionEnvelope)
def submit_session(payload: SessionSubmitRequest, background_tasks: BackgroundTasks) -> SessionEnvelope:
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
    allowed_question_ids = {
        str(question["id"])
        for part in scored_test.get("parts") or []
        for group in part.get("groups") or []
        for question in group.get("questions") or []
    }
    unexpected_timing_keys = sorted(
        set(payload.question_elapsed_seconds) - allowed_question_ids
    )
    if unexpected_timing_keys:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unexpected_question_timing_keys",
                "question_ids": unexpected_timing_keys,
            },
        )
    unexpected_part_timing_keys = sorted(
        set(payload.part_elapsed_seconds) - {str(number) for number in selected_parts}
    )
    if unexpected_part_timing_keys:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unexpected_part_timing_keys",
                "part_numbers": unexpected_part_timing_keys,
            },
        )
    result = score_submission(
        scored_test,
        payload.answers,
        exam_mode=payload.exam_mode,
        total_elapsed_seconds=payload.elapsed_seconds,
        part_elapsed_seconds=payload.part_elapsed_seconds,
        question_elapsed_seconds=payload.question_elapsed_seconds,
    )
    result["part_numbers"] = selected_parts
    result["timed_out"] = payload.timed_out
    annotations, annotation_warnings = _validated_annotations(
        payload,
        selected_parts=selected_parts,
        authoritative_test=authoritative_test,
    )
    result["annotations"] = annotations
    if annotation_warnings:
        result["annotation_warnings"] = annotation_warnings
    stored = repository.save_or_get(
        user_id=payload.user_id,
        client_submission_id=payload.client_submission_id,
        test_id=payload.test_id,
        result=result,
    )
    if os.getenv("PYTEST_CURRENT_TEST"):
        summary = {
            "status": "skipped",
            "reason": "test_environment",
            "wrong_question_count": len(result.get("wrong_questions") or []),
            "candidate_count": 0,
            "saved_count": 0,
        }
    else:
        summary = {
            "status": "queued",
            "reason": "runs_after_scoring_response",
            "wrong_question_count": len(result.get("wrong_questions") or []),
            "candidate_count": 0,
            "saved_count": 0,
        }
        background_tasks.add_task(
            _extract_and_persist_paraphrases,
            database_path=repository.database_path,
            user_id=payload.user_id,
            session_id=stored.id,
            scored_result=dict(result),
        )
    result["ai_paraphrase_summary"] = summary
    stored = repository.update_result(
        user_id=payload.user_id,
        session_id=stored.id,
        result=result,
    ) or stored
    return _envelope(stored)


@router.get("", response_model=list[SessionSummary])
def list_sessions(
    user_id: str = Query(default="owner", min_length=1, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
    include_archived: bool = False,
) -> list[SessionSummary]:
    rows = session_repository().list_recent(
        user_id=user_id, limit=limit, include_archived=include_archived
    )
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
            archived=row.archived_at is not None,
        )
        for row in rows
    ]


@router.post("/delete-batch")
def delete_sessions_batch(payload: SessionDeleteBatchRequest) -> dict[str, Any]:
    deleted_ids, missing_ids = session_repository().delete_many(
        user_id=payload.user_id,
        session_ids=payload.session_ids,
    )
    return {
        "deleted_count": len(deleted_ids),
        "deleted_ids": deleted_ids,
        "missing_ids": missing_ids,
        "recoverable": False,
    }


@router.get("/{session_id}", response_model=SessionEnvelope)
def get_session(
    session_id: str,
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> SessionEnvelope:
    stored = session_repository().get(user_id=user_id, session_id=session_id)
    if not stored:
        raise HTTPException(status_code=404, detail="Session not found")
    return _envelope(stored)


@router.delete("/{session_id}")
def delete_session(
    session_id: str,
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> dict[str, Any]:
    if not session_repository().delete(user_id=user_id, session_id=session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True, "recoverable": False}


@router.post("/{session_id}/restore")
def restore_session(
    session_id: str,
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> dict[str, Any]:
    if not session_repository().restore(user_id=user_id, session_id=session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"restored": True}
