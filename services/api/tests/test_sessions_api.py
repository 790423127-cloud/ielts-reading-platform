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
    answers = _official_answers(test)
    question_ids = list(answers)
    payload = {
        "user_id": "owner",
        "test_id": "b10-test-a",
        "client_submission_id": "submission-full-0001",
        "answers": answers,
        "elapsed_seconds": 3120,
        "part_elapsed_seconds": {"1": 910, "2": 1010, "3": 1200},
        "question_elapsed_seconds": {
            question_id: index + 1
            for index, question_id in enumerate(question_ids)
        },
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
    assert first_data["result"]["question_results"][0]["elapsed_seconds"] == 1
    assert first_data["result"]["question_results"][-1]["elapsed_seconds"] == 40
    assert [part["elapsed_seconds"] for part in first_data["result"]["part_results"]] == [
        910,
        1010,
        1200,
    ]

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


def test_b5_full_mock_accepts_detailed_timing_and_camel_case_aliases(
    monkeypatch, tmp_path
) -> None:
    client = _client(monkeypatch, tmp_path)
    test = QuestionBank(BANK_ROOT).load_server_test("b5-test-a")
    answers = _official_answers(test)
    question_ids = list(answers)

    response = client.post(
        "/api/v1/sessions/submit",
        json={
            "user_id": "owner",
            "test_id": "b5-test-a",
            "client_submission_id": "submission-b5-full-0001",
            "answers": answers,
            "elapsed_seconds": 3707,
            "partElapsedSeconds": {"1": 1200, "2": 1200, "3": 1307},
            "questionElapsedSeconds": {
                question_id: index + 1
                for index, question_id in enumerate(question_ids)
            },
            "exam_mode": "mock_exam",
            "part_numbers": [],
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["test_id"] == "b5-test-a"
    assert result["total"] == 40
    assert result["score"] == 40
    assert len(result["question_results"]) == 40


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
            "part_elapsed_seconds": {"1": 900},
            "exam_mode": "part_practice",
            "part_numbers": [1],
        },
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["score"] == result["total"]
    assert 1 <= result["total"] < 40
    assert result["part_numbers"] == [1]
    assert result["part_results"][0]["elapsed_seconds"] == 900
    assert result["band_estimate"]["eligible"] is False
    assert "estimated_gt_reading_band" not in result


def test_invalid_legacy_annotation_does_not_block_scored_submission(
    monkeypatch, tmp_path
) -> None:
    client = _client(monkeypatch, tmp_path)
    test = QuestionBank(BANK_ROOT).load_server_test("b10-test-a")
    response = client.post(
        "/api/v1/sessions/submit",
        json={
            "user_id": "owner",
            "test_id": "b10-test-a",
            "client_submission_id": "submission-legacy-annotation",
            "answers": _official_answers(test, {1}),
            "exam_mode": "part_practice",
            "part_numbers": [1],
            "annotations": [
                {"id": "old-row-with-missing-fields"},
                {
                    "id": "wrong-test-row",
                    "kind": "highlight",
                    "testId": "another-test",
                    "testTitle": "旧草稿",
                    "partNumber": 1,
                    "paragraphIndex": 0,
                    "startOffset": 0,
                    "endOffset": 4,
                    "selectedText": "text",
                    "prefix": "",
                    "suffix": "",
                    "sentence": "text",
                    "note": "",
                    "createdAt": "2026-07-27T00:00:00Z",
                    "updatedAt": "2026-07-27T00:00:00Z",
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["score"] == result["total"]
    assert result["annotations"] == []
    assert [row["code"] for row in result["annotation_warnings"]] == [
        "invalid_annotation_ignored",
        "annotation_test_mismatch_ignored",
    ]


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


def test_validation_error_returns_readable_field_message(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/sessions/submit",
        json={
            "test_id": "b10-test-a",
            "client_submission_id": "submission-invalid-answers",
            "answers": 7,
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "request_validation_failed"
    assert "answers" in detail["message"]
    assert detail["errors"][0]["loc"][-1] == "answers"


def test_unknown_question_timing_key_is_rejected(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/sessions/submit",
        json={
            "test_id": "b10-test-a",
            "client_submission_id": "submission-invalid-timing",
            "answers": {},
            "question_elapsed_seconds": {"not-a-real-question": 12},
            "exam_mode": "part_practice",
            "part_numbers": [1],
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unexpected_question_timing_keys"


def test_unknown_part_timing_key_is_rejected(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/sessions/submit",
        json={
            "test_id": "b10-test-a",
            "client_submission_id": "submission-invalid-part-timing",
            "answers": {},
            "part_elapsed_seconds": {"2": 12},
            "exam_mode": "part_practice",
            "part_numbers": [1],
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unexpected_part_timing_keys"
