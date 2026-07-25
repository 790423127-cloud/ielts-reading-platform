from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.services.question_bank import QuestionBank, QuestionBankNotReadyError

router = APIRouter(prefix="/question-bank", tags=["question-bank"])


def question_bank() -> QuestionBank:
    root = Path(
        os.getenv(
            "QUESTION_BANK_DIR",
            str(Path(__file__).resolve().parents[2] / "data" / "question-bank"),
        )
    )
    return QuestionBank(root)


@router.get("/migration-status")
def migration_status() -> dict:
    return question_bank().migration_status()


@router.get("/tests")
def list_tests() -> dict:
    try:
        return {"items": question_bank().index()}
    except QuestionBankNotReadyError as error:
        raise HTTPException(status_code=503, detail={"code": "question_bank_migration_incomplete", "message": str(error)}) from error


@router.get("/tests/{test_id}")
def get_public_test(test_id: str) -> dict:
    try:
        return question_bank().load_public_test(test_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Test not found") from error
    except QuestionBankNotReadyError as error:
        raise HTTPException(status_code=503, detail={"code": "question_bank_migration_incomplete", "message": str(error)}) from error
