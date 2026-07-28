from __future__ import annotations

import os
from pathlib import Path
import sqlite3

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.api.question_bank import question_bank
from app.core.config import settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str
    migrationPhase: str
    databaseConnected: bool
    features: dict[str, bool]


class ReadinessResponse(BaseModel):
    ready: bool
    questionBankReady: bool
    foundTests: int
    expectedTests: int
    databaseFilePresent: bool
    databaseReadable: bool
    schemaCompatible: bool
    missingTables: list[str]


REQUIRED_TABLES = {
    "sessions",
    "app_settings",
    "learning_tasks",
    "task_attempts",
    "review_schedule",
    "wrong_question_feedback",
    "skill_mastery",
    "sentence_training_attempts",
    "personal_sentences",
    "vocabulary_items",
    "vocabulary_sources",
    "ai_teacher_conversations",
    "ai_teacher_messages",
    "ai_teacher_cache",
    "durable_ai_jobs",
    "durable_ai_job_items",
    "teacher_assignments",
    "teacher_assignment_modules",
    "teacher_assignment_sessions",
    "teacher_report_snapshots",
}


def _database_readiness() -> tuple[bool, bool, bool, list[str]]:
    database_path = Path(
        os.getenv(
            "SESSION_DB_PATH",
            str(Path(__file__).resolve().parents[2] / "data" / "sessions.sqlite3"),
        )
    )
    if not database_path.is_file():
        return False, False, False, sorted(REQUIRED_TABLES)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
        existing = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing = sorted(REQUIRED_TABLES - existing)
        return True, True, not missing, missing
    except sqlite3.Error:
        return True, False, False, sorted(REQUIRED_TABLES)
    finally:
        if connection is not None:
            connection.close()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    # Importing and probing the application must not create or connect a database.
    return HealthResponse(
        ok=True,
        service=settings.app_name,
        version=settings.app_version,
        migrationPhase=settings.migration_phase,
        databaseConnected=False,
        features={
            "nextAppRouter": True,
            "sharedContracts": True,
            "sharedContractsEnforced": False,
            "legacyHashRouter": False,
            "deterministicScoringCore": True,
            "gtBandParity": True,
            "idempotentUserSessions": True,
            "scoringParity": True,
            "questionBankMigrated": True,
            "questionBankHashGuard": True,
            "realTestParityCases": True,
            "examWorkbench": True,
            "serverScoredSubmission": True,
            "fullMockTimer": True,
            "localDraftRestore": True,
            "sessionHistory": True,
            "wrongQuestionReview": True,
            "fixedMethodCourses": True,
            "abilityTraining": True,
            "learningPlan": True,
            "sentenceTraining": True,
            "personalSentences": True,
            "readingAnnotations": True,
            "vocabularyBook": True,
            "evidenceConstrainedAiTeacher": True,
            "verifiedQuestionOnly": True,
            "exactQuestionTypePractice": True,
            "wrongQuestionDeepLinks": True,
            "deterministicStageReports": True,
            "learningDataMigrationTool": True,
            "teacherAssignments": True,
            "teacherReportSnapshots": True,
            "printableTeacherReports": True,
            "formalReports": True,
            "browserAcceptanceTests": True,
            "authentication": False,
            "localSingleUserMode": True,
            "multiUserFeaturesDeferred": True,
            "replacementReady": False,
            "methodCourseAI": False,
            "voiceFeatures": False,
        },
    )


@router.get("/readiness", response_model=ReadinessResponse)
def readiness(response: Response) -> ReadinessResponse:
    bank_status = question_bank().migration_status()
    database_present, database_readable, schema_compatible, missing_tables = (
        _database_readiness()
    )
    ready = bool(bank_status["ready"] and database_readable and schema_compatible)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        ready=ready,
        questionBankReady=bool(bank_status["ready"]),
        foundTests=int(bank_status["found_tests"]),
        expectedTests=int(bank_status["expected_tests"]),
        databaseFilePresent=database_present,
        databaseReadable=database_readable,
        schemaCompatible=schema_compatible,
        missingTables=missing_tables,
    )
