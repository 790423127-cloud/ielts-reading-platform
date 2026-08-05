from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.domain.ability_training import (
    METHOD_SUMMARY_BY_SUBTYPE,
    QUESTION_TYPE_TARGETS,
    SKILLS,
    build_authoritative_ability_test,
    generate_ability_set,
    skill_catalog,
)
from app.domain.legacy_method_courses import build_method_course_catalog
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


def test_question_type_training_catalog_has_all_17_supported_subtypes() -> None:
    assert len(QUESTION_TYPE_TARGETS) == 17
    assert len({target.subtype_ids[0] for target in QUESTION_TYPE_TARGETS}) == 17
    assert all(target.id.startswith("subtype-") for target in QUESTION_TYPE_TARGETS)
    assert METHOD_SUMMARY_BY_SUBTYPE == {
        item["id"]: item["summary"]
        for item in build_method_course_catalog()["courses"]
    }


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
        "question_elapsed_seconds": {
            question_ref: (index + 1) * 10
            for index, question_ref in enumerate(refs)
        },
    }

    first = client.post("/api/v1/ability/submit", json=payload)
    assert first.status_code == 200
    data = first.json()
    assert data["idempotent_replay"] is False
    assert data["result"]["score"] == data["result"]["total"] == 4
    assert data["result"]["skill_id"] == "answer-boundary"
    assert data["result"]["source_policy"] == "verified_question_bank_only"
    assert [row["elapsed_seconds"] for row in data["result"]["question_results"]] == [
        10,
        20,
        30,
        40,
    ]
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

    invalid_timing = client.post(
        "/api/v1/ability/submit",
        json={
            "client_submission_id": "ability-invalid-timing-0001",
            "skill_id": "main-detail",
            "question_refs": refs,
            "answers": {},
            "question_elapsed_seconds": {"invented-question": 12},
        },
    )
    assert invalid_timing.status_code == 400
    assert invalid_timing.json()["detail"]["code"] == "unexpected_question_timing_keys"


def test_question_type_training_and_exact_question_replay_use_same_secure_pipeline(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("QUESTION_BANK_DIR", str(BANK_ROOT))
    monkeypatch.setenv("SESSION_DB_PATH", str(tmp_path / "question-type.sqlite3"))
    client = TestClient(app)

    catalog_response = client.get("/api/v1/ability/skills")
    assert catalog_response.status_code == 200
    catalog = catalog_response.json()
    assert catalog["count"] == 7
    assert catalog["question_type_count"] == 17
    assert len(catalog["question_types"]) == 17

    target_id = "subtype-true_false_not_given"
    generated_response = client.post(
        "/api/v1/ability/generate",
        json={"skill_id": target_id, "count": 2, "cursor": 0},
    )
    assert generated_response.status_code == 200
    generated = generated_response.json()
    assert generated["training_kind"] == "question_type"
    assert all(
        item["group"]["question_subtype"] == "true_false_not_given"
        for item in generated["items"]
    )
    _assert_public(generated)

    exact_ref = generated["items"][1]["ref_id"]
    exact_response = client.post(
        "/api/v1/ability/generate",
        json={
            "skill_id": target_id,
            "count": 1,
            "cursor": 0,
            "question_refs": [exact_ref],
        },
    )
    assert exact_response.status_code == 200
    exact = exact_response.json()
    assert exact["exact_question_replay"] is True
    assert [item["ref_id"] for item in exact["items"]] == [exact_ref]
    _assert_public(exact)

    authoritative = build_authoritative_ability_test(
        QuestionBank(BANK_ROOT),
        skill_id=target_id,
        question_refs=[exact_ref],
    )
    submit_response = client.post(
        "/api/v1/ability/submit",
        json={
            "client_submission_id": "question-type-exact-0001",
            "skill_id": target_id,
            "question_refs": [exact_ref],
            "answers": _official_answers(authoritative),
            "elapsed_seconds": 30,
            "question_elapsed_seconds": {exact_ref: 30},
        },
    )
    assert submit_response.status_code == 200
    result = submit_response.json()["result"]
    assert result["practice_mode"] == "question_type"
    assert result["training_kind"] == "question_type"
    assert result["question_results"][0]["elapsed_seconds"] == 30
    assert result["question_results"][0]["source_question_id"]
    assert result["question_results"][0]["source_part_number"] in {1, 2, 3}
