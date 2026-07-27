from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.question_bank import ANSWER_FIELDS, QuestionBank, expected_test_index


def fixture_test() -> dict:
    return {
        "id": "b10-test-a",
        "title": "Fixture",
        "parts": [
            {
                "number": 1,
                "groups": [
                    {
                        "instructions": "Do the following statements agree? TRUE FALSE NOT GIVEN",
                        "answer": "group-secret",
                        "evidence": ["group evidence"],
                        "questions": [
                            {
                                "id": "q1",
                                "number": 1,
                                "prompt": "Fixture statement",
                                "answer": "TRUE",
                                "accepted_answers": ["TRUE", "T"],
                                "analysis": "secret analysis",
                                "evidence": ["secret evidence"],
                                "paraphrasing": "secret paraphrase",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_expected_manifest_has_58_complete_tests() -> None:
    index = expected_test_index()
    assert len(index) == 58
    assert sum(item["question_count"] for item in index) == 2320
    assert index[0]["id"] == "b4-test-a"
    assert index[-1]["id"] == "b21-test-4"


def test_public_payload_strips_every_answer_and_explanation_field(tmp_path) -> None:
    root = tmp_path / "question-bank"
    test_dir = root / "tests"
    test_dir.mkdir(parents=True)
    test = fixture_test()
    (test_dir / "b10-test-a.json").write_text(json.dumps(test), "utf-8")
    bank = QuestionBank(root)

    public = bank.load_public_test("b10-test-a")
    group = public["parts"][0]["groups"][0]
    question = group["questions"][0]
    assert ANSWER_FIELDS.isdisjoint(group)
    assert ANSWER_FIELDS.isdisjoint(question)
    assert question["prompt"] == "Fixture statement"
    assert group["question_subtype"] == "true_false_not_given"


def test_server_payload_retains_authoritative_answers(tmp_path) -> None:
    root = tmp_path / "question-bank"
    test_dir = root / "tests"
    test_dir.mkdir(parents=True)
    (test_dir / "b10-test-a.json").write_text(json.dumps(fixture_test()), "utf-8")
    bank = QuestionBank(root)
    server = bank.load_server_test("b10-test-a")
    assert server["parts"][0]["groups"][0]["questions"][0]["answer"] == "TRUE"


def test_legacy_lowercase_l_ocr_confusion_is_repaired_in_question_copy(tmp_path) -> None:
    root = tmp_path / "question-bank"
    test_dir = root / "tests"
    test_dir.mkdir(parents=True)
    test = fixture_test()
    question = test["parts"][0]["groups"][0]["questions"][0]
    question["prompt"] = "lt is visible."
    question["options"] = [{"value": "A", "label": "lt is also visible."}]
    (test_dir / "b10-test-a.json").write_text(json.dumps(test), "utf-8")

    public = QuestionBank(root).load_public_test("b10-test-a")
    repaired = public["parts"][0]["groups"][0]["questions"][0]

    assert repaired["prompt"] == "It is visible."
    assert repaired["options"][0]["label"] == "It is also visible."


def test_verified_passage_layout_repairs_restore_table_structure(tmp_path) -> None:
    root = tmp_path / "question-bank"
    test_dir = root / "tests"
    test_dir.mkdir(parents=True)
    test = fixture_test()
    test["parts"][0]["paragraphs"] = [{"index": 1, "text": "flattened source table"}]
    (test_dir / "b10-test-a.json").write_text(json.dumps(test), "utf-8")
    (root / "passage_layout_repairs.json").write_text(
        json.dumps(
            {
                "repairs": [
                    {
                        "test_id": "b10-test-a",
                        "part_number": 1,
                        "paragraph_index": 1,
                        "table": {
                            "headers": ["Place", "Price"],
                            "rows": [["A", "$10"]],
                        },
                    }
                ]
            }
        ),
        "utf-8",
    )

    public = QuestionBank(root).load_public_test("b10-test-a")

    assert public["parts"][0]["paragraphs"][0]["text"] == "flattened source table"
    assert public["parts"][0]["paragraphs"][0]["table"]["rows"] == [["A", "$10"]]


def test_incomplete_bank_returns_explicit_503(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QUESTION_BANK_DIR", str(tmp_path / "empty"))
    client = TestClient(app)
    status = client.get("/api/v1/question-bank/migration-status")
    assert status.status_code == 200
    assert status.json()["ready"] is False
    response = client.get("/api/v1/question-bank/tests")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "question_bank_migration_incomplete"
