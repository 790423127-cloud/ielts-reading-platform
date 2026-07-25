from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.domain.ability_training import (
    SKILLS,
    build_authoritative_ability_test,
    generate_ability_set,
    skill_catalog,
)
from app.main import app
from app.services.question_bank import ANSWER_FIELDS, QuestionBank

API_ROOT = Path(__file__).resolve().parents[1]
BANK_ROOT = API_ROOT / "data" / "question-bank"


def _assert_public(value: Any) -> None:
    if isinstance(value, dict):
        assert ANSWER_FIELDS.isdisjoint(value.keys())
        for child in value.values():
            _assert_public(child)
    elif isinstance(value, list):
        for child in value:
            _assert_public(child)


def _official_answers(test: dict[str, Any]) -> dict[str, Any]:
    answers: dict[str, Any] = {}
    for part in test.get("parts") or []:
        for group in part.get("groups") or []:
            for question in group.get("questions") or []:
                accepted = [
                    item
                    for item in (question.get("accepted_answers") or [])
                    if str(item).strip()
                ]
                answer = question.get("answer")
                answers[str(question["id"])] = (
                    answer
                    if answer is not None and str(answer).strip()
                    else accepted[0] if accepted else ""
                )
    return answers


def test_catalog_has_exactly_seven_verified_question_skills() -> None:
    catalog = skill_catalog()
    assert len(SKILLS) == len(catalog) == 7
    assert [item["id"] for item in catalog] == [
        "locating",
        "paraphrase",
        "main-detail",
        "scope-degree",
        "time-cause",
        "answer-boundary",
        "spelling-plural",
    ]
    assert all(item["source_policy"].startswith("仅使用") for item in catalog)


def test_every_skill_generates_only_real_public_questions() -> None:
    bank = QuestionBank(BANK_ROOT)
    for skill in SKILLS:
        generated = generate_ability_set(bank, skill_id=skill.id, count=2, cursor=0)
        assert generated["skill"]["id"] == skill.id
        assert generated["source_policy"] == "verified_question_bank_only"
        assert len(generated["items"]) == 2
        for item in generated["items"]:
            assert item["test_id"].startswith("b")
            assert item["ref_id"].startswith(f"{item['test_id']}:")
            assert item["passage"]["paragraphs"]
            assert len(item["group"]["questions"]) == 1
            assert item["group"]["questions"][0]["id"] == item["ref_id"]
            _assert_public(item)


def test_authoritative_ability_set_rebuilds_selected_real_questions() -> None:
    bank = QuestionBank(BANK_ROOT)
    generated = generate_ability_set(bank, skill_id="locating", count=5, cursor=3)
    refs = [item["ref_id"] for item in generated["items"]]
    authoritative = build_authoritative_ability_test(
        bank,
        skill_id="locating",
        question_refs=refs,
    )
    question_ids = [
        str(question["id"])
        for part in authoritative["parts"]
        for group in part["groups"]
        for question in group["questions"]
    ]
    assert question_ids == refs
    assert authoritative["practice_mode"] == "ability"
    assert _official_answers(authoritative).keys() == set(refs)


def test_ability_api_server_scores_real_questions_without_band_and_is_idempotent(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("QUESTION_BANK_DIR", str(BANK_ROOT))
    monkeypatch.setenv("SESSION_DB_PATH", str(tmp_path / "ability.sqlite3"))
    client = TestClient(app)
    generated_response = client.post(
        "/api/v1/ability/generate",
        json={"skill_id": "answer-boundary", "count": 4, "cursor": 0},
    )
    assert generated_response.status_code == 200
    generated = generated_response.json()
    refs = [item["ref_id"] for item in generated["items"]]
    authoritative = build_authoritative_ability_test(
        QuestionBank(BANK_ROOT),
        skill_id="answer-boundary",
        question_refs=refs,
    )
    answers = _official_answers(authoritative)
    payload = {
        "user_id": "owner",
        "client_submission_id": "ability-answer-boundary-0001",
        "skill_id": "answer-boundary",
        "question_refs": refs,
        "answers": answers,
        "elapsed_seconds": 240,
    }

    first = client.post("/api/v1/ability/submit", json=payload)
    assert first.status_code == 200
    data = first.json()
    assert data["idempotent_replay"] is False
    assert data["result"]["score"] == data["result"]["total"] == 4
    assert data["result"]["skill_id"] == "answer-boundary"
    assert data["result"]["source_policy"] == "verified_question_bank_only"
    assert data["result"]["band_estimate"]["eligible"] is False
    assert "estimated_gt_reading_band" not in data["result"]

    replay = client.post(
        "/api/v1/ability/submit",
        json={**payload, "answers": {}},
    )
    assert replay.status_code == 200
    replay_data = replay.json()
    assert replay_data["session_id"] == data["session_id"]
    assert replay_data["idempotent_replay"] is True
    assert replay_data["result"]["score"] == 4


def test_ability_submit_rejects_unexpected_answer_keys(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QUESTION_BANK_DIR", str(BANK_ROOT))
    monkeypatch.setenv("SESSION_DB_PATH", str(tmp_path / "ability-invalid.sqlite3"))
    client = TestClient(app)
    generated = client.post(
        "/api/v1/ability/generate",
        json={"skill_id": "main-detail", "count": 1, "cursor": 0},
    ).json()
    refs = [generated["items"][0]["ref_id"]]
    response = client.post(
        "/api/v1/ability/submit",
        json={
            "client_submission_id": "ability-invalid-0001",
            "skill_id": "main-detail",
            "question_refs": refs,
            "answers": {"invented-question": "A"},
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unexpected_answer_keys"
