from fastapi.testclient import TestClient

from app.main import app, create_app
from app.repositories.ai_teacher_repository import AiTeacherRepository
from app.repositories.ai_job_repository import AiJobRepository
from app.repositories.learning_plan_repository import LearningPlanRepository
from app.repositories.review_feedback_repository import ReviewFeedbackRepository
from app.repositories.sentence_repository import SentenceRepository
from app.repositories.session_repository import SQLiteSessionRepository
from app.repositories.teacher_repository import TeacherRepository
from app.repositories.vocabulary_repository import VocabularyRepository


def test_health_does_not_connect_database() -> None:
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["version"] == "1.0.0"
    assert payload["migrationPhase"] == "replacement_validation"
    assert payload["databaseConnected"] is False
    assert payload["features"]["nextAppRouter"] is True
    assert payload["features"]["legacyHashRouter"] is False
    assert payload["features"]["learningPlan"] is True
    assert payload["features"]["sentenceTraining"] is True
    assert payload["features"]["vocabularyBook"] is True
    assert payload["features"]["evidenceConstrainedAiTeacher"] is True
    assert payload["features"]["sharedContractsEnforced"] is True
    assert payload["features"]["replacementReady"] is False
    assert payload["features"]["browserAcceptanceTests"] is True
    assert payload["features"]["formalReports"] is True
    assert payload["features"]["localSingleUserMode"] is True
    assert payload["features"]["multiUserFeaturesDeferred"] is True


def test_readiness_is_read_only_and_reports_missing_database(tmp_path, monkeypatch) -> None:
    missing = tmp_path / "missing.sqlite3"
    monkeypatch.setenv("SESSION_DB_PATH", str(missing))

    response = TestClient(create_app()).get("/api/v1/readiness")

    assert response.status_code == 503
    assert response.json()["databaseFilePresent"] is False
    assert response.json()["schemaCompatible"] is False
    assert not missing.exists()


def test_readiness_accepts_complete_local_schema(tmp_path, monkeypatch) -> None:
    database = tmp_path / "ready.sqlite3"
    monkeypatch.setenv("SESSION_DB_PATH", str(database))
    SQLiteSessionRepository(database)
    LearningPlanRepository(database)
    SentenceRepository(database)
    VocabularyRepository(database)
    AiTeacherRepository(database)
    AiJobRepository(database)
    TeacherRepository(database)
    ReviewFeedbackRepository(database)

    response = TestClient(create_app()).get("/api/v1/readiness")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["missingTables"] == []
