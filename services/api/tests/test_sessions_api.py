from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.services.question_bank import QuestionBank

API_ROOT = Path(__file__).resolve().parents[1]
BANK_ROOT = API_ROOT / "data" / "question-bank"


def _official_answers(test: dict[str, Any], part_numbers: set[int] | None = None) -> dict[str, Any]:
    answers: dict[str, Any] = {}
    for part in test.get("parts") or []:
        if part_numbers and int(part.get("number") or 0) not in part_numbers:
            continue
        for group in part.get("groups") or []:
            for question in group.get("questions") or []:
                accepted = [
                    item
                    for item in (question.get("accepted_answers") or [])
                    if str(item).strip()
                ]
                answer = question.get("answer")
                answers[str(question["id"])] = (
                    answer if answer is not None and str(answer).strip()
                    else accepted[0] if accepted else ""
                )
    return answers


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("QUESTION_BANK_DIR", str(BANK_ROOT))
    monkeypatch.setenv("SESSION_DB_PATH", str(tmp_path / "sessions.sqlite3"))
    return TestClient(app)


def test_full_mock_submission_is_server_scored_idempotent_and_persisted(
    monkeypatch, tmp_path
) -> None:
    client = _client(monkeypatch, tmp_path)
    test = QuestionBank(BANK_ROOT).load_server_test("b10-test-a")
    payload = {
        "user_id": "owner",
        "test_id": "b10-test-a",
        "client_submission_id": "submission-full-0001",
        "answers": _official_answers(test),
        "elapsed_seconds": 3120,
        "exam_mode": "mock_exam",
        "part_numbers": [],
    }

    first = client.post("/api/v1/sessions/submit", json=payload)
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["idempotent_replay"] is False
    assert first_data["result"]["score"] == 40
    assert first_data["result"]["total"] == 40
    assert first_data["result"]["estimated_gt_reading_band"] == 9.0
    assert first_data["result"]["band_estimate"]["eligible"] is True
    assert len(first_data["result"]["question_results"]) == 40
    assert all("correct_answer" in row for row in first_data["result"]["question_results"])

    replay_payload = {**payload, "answers": {}}
    replay = client.post("/api/v1/sessions/submit", json=replay_payload)
    assert replay.status_code == 200
    replay_data = replay.json()
    assert replay_data["session_id"] == first_data["session_id"]
    assert replay_data["idempotent_replay"] is True
    assert replay_data["result"]["score"] == 40

    history = client.get("/api/v1/sessions", params={"user_id": "owner"})
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["session_id"] == first_data["session_id"]
    assert history.json()[0]["estimated_band"] == 9.0

    detail = client.get(
        f"/api/v1/sessions/{first_data['session_id']}",
        params={"user_id": "owner"},
    )
    assert detail.status_code == 200
    assert detail.json()["result"]["score"] == 40

    other_user = client.get("/api/v1/sessions", params={"user_id": "another-user"})
    assert other_user.status_code == 200
    assert other_user.json() == []


def test_part_submission_scores_only_selected_part_and_never_returns_band(
    monkeypatch, tmp_path
) -> None:
    client = _client(monkeypatch, tmp_path)
    test = QuestionBank(BANK_ROOT).load_server_test("b10-test-a")
    response = client.post(
        "/api/v1/sessions/submit",
        json={
            "user_id": "owner",
            "test_id": "b10-test-a",
            "client_submission_id": "submission-part-0001",
            "answers": _official_answers(test, {1}),
            "elapsed_seconds": 900,
            "exam_mode": "part_practice",
            "part_numbers": [1],
        },
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["score"] == result["total"]
    assert 1 <= result["total"] < 40
    assert result["part_numbers"] == [1]
    assert result["band_estimate"]["eligible"] is False
    assert "estimated_gt_reading_band" not in result


def test_invalid_part_and_unknown_test_are_rejected(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    invalid_part = client.post(
        "/api/v1/sessions/submit",
        json={
            "test_id": "b10-test-a",
            "client_submission_id": "submission-invalid-part",
            "answers": {},
            "exam_mode": "part_practice",
            "part_numbers": [9],
        },
    )
    assert invalid_part.status_code == 400
    assert invalid_part.json()["detail"]["code"] == "invalid_part_numbers"

    missing = client.post(
        "/api/v1/sessions/submit",
        json={
            "test_id": "missing-test",
            "client_submission_id": "submission-missing-test",
            "answers": {},
        },
    )
    assert missing.status_code == 404
