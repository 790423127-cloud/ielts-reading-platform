from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.session_repository import SQLiteSessionRepository
from app.services.sentence_training import SentenceTrainingBank

API_ROOT = Path(__file__).resolve().parents[1]
TRAINING_ROOT = API_ROOT / "data" / "sentence-training"


def _submitted_wrong_session(
    database: Path,
    *,
    evidence: str,
    question_id: str = "question-1",
) -> str:
    repository = SQLiteSessionRepository(database)
    stored = repository.save_or_get(
        user_id="owner",
        client_submission_id=f"session-for-{question_id}",
        test_id="b10-test-a",
        result={
            "test_id": "b10-test-a",
            "test_title": "剑雅10 Test A",
            "exam_mode": "mock_exam",
            "score": 0,
            "total": 1,
            "question_results": [
                {
                    "id": question_id,
                    "number": 1,
                    "part_number": 1,
                    "question_type": "判断题",
                    "question_subtype": "true_false_not_given",
                    "prompt": "A wrong question",
                    "user_answer": "FALSE",
                    "correct_answer": "TRUE",
                    "is_correct": False,
                    "answer_error_type": "incorrect",
                    "evidence": [evidence],
                }
            ],
        },
    )
    return stored.id


def _client(monkeypatch, tmp_path) -> tuple[TestClient, Path]:
    database = tmp_path / "personal-sentences.sqlite3"
    monkeypatch.setenv("SESSION_DB_PATH", str(database))
    monkeypatch.setenv("SENTENCE_TRAINING_DIR", str(TRAINING_ROOT))
    return TestClient(app), database


def test_manual_sentence_is_self_only_and_never_gets_standard_parse(monkeypatch, tmp_path) -> None:
    client, _ = _client(monkeypatch, tmp_path)
    verified_sentence = SentenceTrainingBank(TRAINING_ROOT).items()[0]["sentence"]
    response = client.post(
        "/api/v1/sentences",
        json={
            "sentence": verified_sentence,
            "source_type": "manual",
            "previous_sentence": "Previous context.",
            "next_sentence": "Next context.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["permission"] == "self_only"
    assert data["standard_parse"] is None
    assert data["standard_parse_available"] is False
    assert data["analysis_allowed"] is True

    update = client.put(
        f"/api/v1/sentences/{data['id']}/analysis",
        json={
            "predicate": "my predicate",
            "subject": "my subject",
            "object": "",
            "scope": "my scope",
            "logic": "contrast",
            "note": "My own analysis, not a standard answer.",
        },
    )
    assert update.status_code == 200
    updated = update.json()
    assert updated["analysis"]["predicate"] == "my predicate"
    assert updated["standard_parse"] is None


def test_duplicate_capture_returns_same_sentence_record(monkeypatch, tmp_path) -> None:
    client, _ = _client(monkeypatch, tmp_path)
    payload = {
        "sentence": "A manually pasted complex sentence for deduplication.",
        "source_type": "manual",
    }
    first = client.post("/api/v1/sentences", json=payload)
    second = client.post("/api/v1/sentences", json=payload)
    assert first.status_code == second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["deduplicated"] is True
    listing = client.get("/api/v1/sentences")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1


def test_active_mock_mark_is_locked_until_submitted_session_exists(monkeypatch, tmp_path) -> None:
    client, _ = _client(monkeypatch, tmp_path)
    captured = client.post(
        "/api/v1/sentences",
        json={
            "sentence": "A sentence marked while the mock is still active.",
            "source_type": "mock_mark",
            "test_id": "b10-test-a",
            "part_number": 1,
            "exam_mode": "mock_exam",
        },
    )
    assert captured.status_code == 200
    item = captured.json()
    assert item["permission"] == "locked"
    assert item["analysis_allowed"] is False
    assert item["standard_parse"] is None

    analysis = client.put(
        f"/api/v1/sentences/{item['id']}/analysis",
        json={"predicate": "cannot analyse yet"},
    )
    assert analysis.status_code == 409
    assert analysis.json()["detail"]["code"] == "analysis_locked_until_submission"


def test_verified_wrong_evidence_unlocks_reviewed_standard_parse(monkeypatch, tmp_path) -> None:
    client, database = _client(monkeypatch, tmp_path)
    verified = SentenceTrainingBank(TRAINING_ROOT).items()[0]
    session_id = _submitted_wrong_session(
        database,
        evidence=verified["sentence"],
        question_id="verified-question",
    )
    response = client.post(
        "/api/v1/sentences",
        json={
            "sentence": verified["sentence"],
            "source_type": "wrong_evidence",
            "source_session_id": session_id,
            "source_question_id": "verified-question",
            "test_id": "b10-test-a",
            "test_title": "剑雅10 Test A",
            "part_number": 1,
            "exam_mode": "mock_exam",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["permission"] == "verified"
    assert data["verified_item_id"] == verified["id"]
    assert data["standard_parse_available"] is True
    assert data["standard_parse_label"] == "审核标准拆解"
    assert data["standard_parse"]["subject"] == verified["roles"]["subject"]
    assert data["standard_parse"]["predicate"] == verified["roles"]["predicate"]


def test_unreviewed_wrong_evidence_allows_self_analysis_but_no_standard(monkeypatch, tmp_path) -> None:
    client, database = _client(monkeypatch, tmp_path)
    evidence = "This evidence sentence is real in the submitted result but not in the fixed reviewed bank."
    session_id = _submitted_wrong_session(
        database,
        evidence=evidence,
        question_id="unreviewed-question",
    )
    response = client.post(
        "/api/v1/sentences",
        json={
            "sentence": evidence,
            "source_type": "wrong_evidence",
            "source_session_id": session_id,
            "source_question_id": "unreviewed-question",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["permission"] == "self_only"
    assert data["analysis_allowed"] is True
    assert data["standard_parse"] is None
    assert data["ai_analysis_available"] is False


def test_wrong_evidence_must_match_submitted_question_evidence(monkeypatch, tmp_path) -> None:
    client, database = _client(monkeypatch, tmp_path)
    session_id = _submitted_wrong_session(
        database,
        evidence="The exact verified evidence sentence.",
        question_id="mismatch-question",
    )
    response = client.post(
        "/api/v1/sentences",
        json={
            "sentence": "A different sentence invented by the client.",
            "source_type": "wrong_evidence",
            "source_session_id": session_id,
            "source_question_id": "mismatch-question",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "evidence_sentence_mismatch"
