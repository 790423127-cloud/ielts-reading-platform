from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import app.api.ai_teacher as ai_teacher_api
from app.main import app
from app.repositories.session_repository import SQLiteSessionRepository


def _client(monkeypatch, tmp_path) -> tuple[TestClient, Path]:
    database = tmp_path / "ai-teacher.sqlite3"
    monkeypatch.setenv("SESSION_DB_PATH", str(database))
    monkeypatch.setenv("AI_DAILY_REQUEST_LIMIT", "5")
    return TestClient(app), database


def _wrong_session(database: Path, *, user_id: str = "owner") -> str:
    repository = SQLiteSessionRepository(database)
    stored = repository.save_or_get(
        user_id=user_id,
        client_submission_id=f"ai-session-{user_id}",
        test_id="b10-test-a",
        result={
            "test_id": "b10-test-a",
            "test_title": "剑雅10 Test A",
            "exam_mode": "mock_exam",
            "score": 0,
            "total": 1,
            "question_results": [
                {
                    "id": "question-1",
                    "number": 1,
                    "part_number": 1,
                    "question_type": "判断题",
                    "question_subtype": "true_false_not_given",
                    "prompt": "The project was completed before 2010.",
                    "user_answer": "TRUE",
                    "correct_answer": "FALSE",
                    "is_correct": False,
                    "answer_error_type": "incorrect",
                    "analysis": "题干时间与原文不一致。",
                    "paraphrasing": "completed = finished",
                    "evidence": ["The project was not finished until 2012."],
                }
            ],
        },
    )
    return stored.id


def test_wrong_question_uses_server_context_and_exact_cache(monkeypatch, tmp_path) -> None:
    client, database = _client(monkeypatch, tmp_path)
    session_id = _wrong_session(database)
    calls: list[dict] = []

    def fake_generate(**kwargs):
        calls.append(kwargs)
        return {
            "answer": "原文说直到2012年才完成，所以题干的before 2010与原文矛盾。",
            "model": "test-model",
            "input_tokens": 120,
            "output_tokens": 30,
            "provider_request_id": "response-test-1",
        }

    monkeypatch.setattr(ai_teacher_api, "generate_ai_reply", fake_generate)
    payload = {
        "context_type": "wrong_question",
        "session_id": session_id,
        "question_id": "question-1",
        "question": "我为什么错了？",
    }
    first = client.post("/api/v1/ai-teacher/chat", json=payload)
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["cached"] is False
    assert first_data["policy"]["can_change_answer_or_score"] is False
    assert first_data["policy"]["can_mark_mastery"] is False
    assert len(calls) == 1
    context = calls[0]["context"]
    assert context["source"] == "submitted_session"
    assert context["question"]["correct_answer"] == "FALSE"
    assert context["question"]["evidence"] == ["The project was not finished until 2012."]

    second = client.post("/api/v1/ai-teacher/chat", json=payload)
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["cached"] is True
    assert second_data["answer"] == first_data["answer"]
    assert len(calls) == 1
    assert second_data["conversation"]["usage"]["provider_calls"] == 1
    assert second_data["conversation"]["usage"]["cache_hits"] == 1


def test_wrong_question_must_exist_in_submitted_owner_session(monkeypatch, tmp_path) -> None:
    client, database = _client(monkeypatch, tmp_path)
    session_id = _wrong_session(database, user_id="owner")
    response = client.post(
        "/api/v1/ai-teacher/chat",
        json={
            "user_id": "other",
            "context_type": "wrong_question",
            "session_id": session_id,
            "question_id": "question-1",
            "question": "解释这道题",
        },
    )
    assert response.status_code == 404


def test_locked_sentence_rejects_ai_analysis(monkeypatch, tmp_path) -> None:
    client, _ = _client(monkeypatch, tmp_path)
    captured = client.post(
        "/api/v1/sentences",
        json={
            "sentence": "A sentence selected while a mock exam is still active.",
            "source_type": "mock_mark",
            "test_id": "b10-test-a",
            "part_number": 1,
            "exam_mode": "mock_exam",
        },
    )
    assert captured.status_code == 200
    assert captured.json()["permission"] == "locked"

    response = client.post(
        "/api/v1/ai-teacher/chat",
        json={
            "context_type": "sentence",
            "sentence_id": captured.json()["id"],
            "question": "帮我拆解这个句子",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ai_locked_until_submission"


def test_plan_chat_cannot_change_mastery_and_conversations_are_user_isolated(monkeypatch, tmp_path) -> None:
    client, database = _client(monkeypatch, tmp_path)
    _wrong_session(database)
    captured_contexts: list[dict] = []

    def fake_generate(**kwargs):
        captured_contexts.append(kwargs["context"])
        return {
            "answer": "先完成系统排在最前面的真实题训练；我不能替你标记完成。",
            "model": "test-model",
            "input_tokens": 80,
            "output_tokens": 20,
            "provider_request_id": "response-plan-1",
        }

    monkeypatch.setattr(ai_teacher_api, "generate_ai_reply", fake_generate)
    before = client.get("/api/v1/plan").json()
    response = client.post(
        "/api/v1/ai-teacher/chat",
        json={"context_type": "plan", "question": "我今天先做什么？"},
    )
    assert response.status_code == 200
    assert captured_contexts[0]["ai_permissions"]["can_mark_mastery"] is False
    assert captured_contexts[0]["ai_permissions"]["can_change_task_status"] is False
    after = client.get("/api/v1/plan").json()
    assert [(row["id"], row["status"]) for row in before["tasks"]] == [
        (row["id"], row["status"]) for row in after["tasks"]
    ]

    owner_list = client.get("/api/v1/ai-teacher/conversations").json()
    other_list = client.get("/api/v1/ai-teacher/conversations?user_id=other").json()
    assert owner_list["count"] == 1
    assert owner_list["items"][0]["summary"]
    assert other_list["count"] == 0

    forbidden = client.get(
        f"/api/v1/ai-teacher/conversations/{owner_list['items'][0]['id']}?user_id=other"
    )
    assert forbidden.status_code == 404


def test_unconfigured_provider_returns_clear_error(monkeypatch, tmp_path) -> None:
    client, _ = _client(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/api/v1/ai-teacher/chat",
        json={"context_type": "plan", "question": "给我学习建议"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ai_not_configured"
