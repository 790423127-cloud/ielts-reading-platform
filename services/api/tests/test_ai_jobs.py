from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

from fastapi.testclient import TestClient

import app.api.ai_jobs as ai_jobs_api
from app.main import create_app
from app.repositories.ai_job_repository import AiJobRepository
from app.repositories.session_repository import SQLiteSessionRepository


def _submitted_result() -> dict:
    return {
        "test_id": "b5-test-1",
        "test_title": "Cambridge 5 Test 1",
        "score": 1,
        "total": 2,
        "accuracy": 50,
        "part_numbers": [1],
        "question_results": [
            {
                "id": "q-wrong",
                "number": 1,
                "prompt": "Wrong question",
                "is_correct": False,
                "user_answer": "FALSE",
                "correct_answer": "TRUE",
                "part_number": 1,
                "question_type": "判断题",
                "question_subtype": "TRUE/FALSE/NOT GIVEN",
                "evidence": ["Verified evidence."],
            },
            {
                "id": "q-correct",
                "number": 2,
                "prompt": "Correct question",
                "is_correct": True,
                "user_answer": "TRUE",
                "correct_answer": "TRUE",
                "part_number": 1,
                "question_type": "判断题",
                "question_subtype": "TRUE/FALSE/NOT GIVEN",
            },
        ],
        "wrong_questions": [],
        "part_results": [],
    }


def test_durable_ai_job_is_idempotent_and_only_runs_on_explicit_resume(
    tmp_path, monkeypatch
) -> None:
    database = tmp_path / "durable-ai.sqlite3"
    monkeypatch.setenv("SESSION_DB_PATH", str(database))
    monkeypatch.setenv("AI_PROVIDER", "qwen")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key-never-sent")
    stored = SQLiteSessionRepository(database).save_or_get(
        user_id="owner",
        client_submission_id="durable-ai-session",
        test_id="b5-test-1",
        result=_submitted_result(),
    )
    calls = []

    def fake_chat(payload):
        calls.append(payload.question_id)
        return {
            "answer": "Mock verified explanation",
            "cached": False,
            "provider": "qwen",
            "model": "mock-model",
            "conversation": {"id": "conversation-mock"},
        }

    monkeypatch.setattr(ai_jobs_api, "chat_with_ai_teacher", fake_chat)
    client = TestClient(create_app())
    body = {
        "user_id": "owner",
        "session_id": stored.id,
        "question_ids": ["q-wrong"],
        "idempotency_key": f"session:{stored.id}:wrong:q-wrong",
    }

    created = client.post("/api/v1/ai-jobs", json=body)
    assert created.status_code == 200
    assert created.json()["status"] == "pending"
    assert created.json()["policy"]["creation_calls_ai"] is False
    assert calls == []

    replay = client.post("/api/v1/ai-jobs", json=body)
    assert replay.status_code == 200
    assert replay.json()["id"] == created.json()["id"]
    assert calls == []

    rejected = client.post(
        "/api/v1/ai-jobs",
        json={
            **body,
            "question_ids": ["q-correct"],
            "idempotency_key": f"session:{stored.id}:correct",
        },
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"]["code"] == "wrong_question_required"

    resumed = client.post(
        f"/api/v1/ai-jobs/{created.json()['id']}/resume",
        json={"user_id": "owner"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"
    assert resumed.json()["completed_items"] == 1
    assert resumed.json()["items"][0]["result"]["answer"] == "Mock verified explanation"
    assert calls == ["q-wrong"]

    again = client.post(
        f"/api/v1/ai-jobs/{created.json()['id']}/resume",
        json={"user_id": "owner"},
    )
    assert again.status_code == 200
    assert calls == ["q-wrong"]


def test_expired_ai_job_lease_is_recoverable(tmp_path) -> None:
    database = tmp_path / "lease.sqlite3"
    repository = AiJobRepository(database)
    job = repository.create_or_get(
        user_id="owner",
        session_id="submitted-session",
        idempotency_key="lease-recovery-job",
        provider="qwen",
        model="mock",
        questions=[{"id": "q1", "number": 1}],
    )
    first = repository.claim_next(user_id="owner", job_id=job["id"])
    assert first is not None

    expired = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE durable_ai_job_items SET lease_expires_at=? WHERE id=?",
            (expired, first["id"]),
        )
        connection.commit()

    recovered = repository.claim_next(user_id="owner", job_id=job["id"])
    assert recovered is not None
    assert recovered["id"] == first["id"]
    assert recovered["attempt_count"] == 2
