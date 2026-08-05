from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.session_repository import SQLiteSessionRepository


def _result() -> dict:
    return {
        "test_id": "b5-test-1",
        "test_title": "Cambridge 5 Test 1",
        "score": 1,
        "total": 2,
        "accuracy": 50,
        "part_numbers": [1],
        "part_results": [],
        "wrong_questions": [],
        "question_results": [
            {
                "id": "q1",
                "number": 1,
                "prompt": "Wrong question",
                "is_correct": False,
                "user_answer": "FALSE",
                "correct_answer": "TRUE",
                "part_number": 1,
                "question_type": "判断题",
                "question_subtype": "TRUE/FALSE/NOT GIVEN",
            },
            {
                "id": "q2",
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
    }


def test_student_wrong_cause_is_owned_and_only_accepts_wrong_questions(
    tmp_path, monkeypatch
) -> None:
    database = tmp_path / "review-feedback.sqlite3"
    monkeypatch.setenv("SESSION_DB_PATH", str(database))
    stored = SQLiteSessionRepository(database).save_or_get(
        user_id="owner",
        client_submission_id="review-feedback-session",
        test_id="b5-test-1",
        result=_result(),
    )
    client = TestClient(create_app())

    saved = client.post(
        f"/api/v1/review/wrong-questions/{stored.id}/q1/feedback",
        json={
            "user_id": "owner",
            "match_status": "partial",
            "understanding_status": "needs_review",
            "cause_id": "paraphrase_failure",
            "note": "定位正确，但没有看出同义替换。",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["cause_id"] == "paraphrase_failure"

    reviewed = client.get("/api/v1/review/wrong-questions?user_id=owner")
    assert reviewed.status_code == 200
    item = reviewed.json()["items"][0]
    assert item["student_feedback"]["note"] == "定位正确，但没有看出同义替换。"

    correct = client.post(
        f"/api/v1/review/wrong-questions/{stored.id}/q2/feedback",
        json={
            "user_id": "owner",
            "match_status": "matches",
            "understanding_status": "understood",
        },
    )
    assert correct.status_code == 400
    assert correct.json()["detail"]["code"] == "wrong_question_required"

    other_user = client.post(
        f"/api/v1/review/wrong-questions/{stored.id}/q1/feedback",
        json={
            "user_id": "other-user",
            "match_status": "matches",
            "understanding_status": "understood",
        },
    )
    assert other_user.status_code == 404

    unknown_cause = client.post(
        f"/api/v1/review/wrong-questions/{stored.id}/q1/feedback",
        json={
            "user_id": "owner",
            "match_status": "matches",
            "understanding_status": "understood",
            "cause_id": "invented-cause",
        },
    )
    assert unknown_cause.status_code == 400
    assert unknown_cause.json()["detail"]["code"] == "unknown_cause"
