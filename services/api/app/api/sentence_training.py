from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.sessions import session_repository
from app.repositories.sentence_repository import SentenceRepository
from app.services.sentence_training import (
    STEP_KEYS,
    SentenceTrainingBank,
    SentenceTrainingDataError,
)

router = APIRouter(prefix="/sentence-training", tags=["sentence-training"])


class SentenceTrainingSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    client_submission_id: str = Field(min_length=8, max_length=160)
    item_id: str = Field(min_length=1, max_length=120)
    answers: dict[str, str] = Field(default_factory=dict)


def sentence_training_bank() -> SentenceTrainingBank:
    root = Path(
        os.getenv(
            "SENTENCE_TRAINING_DIR",
            str(Path(__file__).resolve().parents[2] / "data" / "sentence-training"),
        )
    )
    return SentenceTrainingBank(root)


def sentence_repository() -> SentenceRepository:
    return SentenceRepository(session_repository().database_path)


@router.get("")
def list_sentence_training() -> dict[str, Any]:
    try:
        return sentence_training_bank().public_catalog()
    except SentenceTrainingDataError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "sentence_training_data_unavailable", "message": str(error)},
        ) from error


@router.post("/submit")
def submit_sentence_training(payload: SentenceTrainingSubmitRequest) -> dict[str, Any]:
    unexpected = sorted(set(payload.answers) - set(STEP_KEYS))
    if unexpected:
        raise HTTPException(
            status_code=400,
            detail={"code": "unexpected_analysis_keys", "keys": unexpected},
        )
    repository = sentence_repository()
    try:
        result = sentence_training_bank().evaluate(payload.item_id, payload.answers)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Sentence training item not found") from error
    except SentenceTrainingDataError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "sentence_training_data_unavailable", "message": str(error)},
        ) from error
    attempt = repository.save_training_attempt(
        user_id=payload.user_id,
        client_submission_id=payload.client_submission_id,
        item_id=payload.item_id,
        answers=payload.answers,
        result=result,
    )
    return attempt
