from __future__ import annotations

import json
import re
from pathlib import Path

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


def test_local_ieltsbro_source_html_is_attached_by_part_and_group_position(tmp_path) -> None:
    root = tmp_path / "question-bank"
    test_dir = root / "tests"
    test_dir.mkdir(parents=True)
    (test_dir / "b10-test-a.json").write_text(json.dumps(fixture_test()), "utf-8")
    (root / "passage_source_html.local.json").write_text(
        json.dumps(
            {
                "parts": [
                    {
                        "test_id": "b10-test-a",
                        "part_number": 1,
                        "source_name": "C10-Test A-Section 1",
                        "passage_html": "<table><tr><td>Original layout</td></tr></table>",
                        "question_groups": [
                            {
                                "position": 0,
                                "display_start": 1,
                                "display_end": 1,
                                "question_type": 4,
                                "interaction_mode": "stale_wrong_mode",
                                "instructions_html": "Questions 1-7<br><br><strong>TRUE</strong>",
                            },
                            {
                                "position": 1,
                                "display_start": 1,
                                "display_end": 1,
                                "instructions_html": "Question 1<br><br>Second source block",
                            }
                        ],
                    }
                ]
            }
        ),
        "utf-8",
    )

    public = QuestionBank(root).load_public_test("b10-test-a")
    part = public["parts"][0]

    assert part["source_visual_name"] == "C10-Test A-Section 1"
    assert "Original layout" in part["source_html"]
    source_groups = part["groups"][0]["source_question_groups"]
    assert "Questions 1-7" in source_groups[0]["instructions_html"]
    assert source_groups[0]["interaction_mode"] == "matching_matrix"
    assert source_groups[1]["interaction_mode"] == "text_entry"
    assert "Second source block" in source_groups[1]["instructions_html"]


def test_broad_source_range_does_not_leak_into_later_question_groups(tmp_path) -> None:
    root = tmp_path / "question-bank"
    test_dir = root / "tests"
    test_dir.mkdir(parents=True)
    test = fixture_test()
    test["parts"][0]["groups"] = [
        {
            "questions": [
                {"id": "q1", "number": 1, "prompt": "Section A", "answer": "i", "accepted_answers": ["i"]},
                {"id": "q2", "number": 2, "prompt": "Section B", "answer": "ii", "accepted_answers": ["ii"]},
            ]
        },
        {
            "questions": [
                {"id": "q3", "number": 3, "prompt": "Choice", "answer": "A", "accepted_answers": ["A"]},
                {"id": "q4", "number": 4, "prompt": "Choice", "answer": "B", "accepted_answers": ["B"]},
            ]
        },
    ]
    (test_dir / "b10-test-a.json").write_text(json.dumps(test), "utf-8")
    (root / "passage_source_html.local.json").write_text(
        json.dumps(
            {
                "parts": [
                    {
                        "test_id": "b10-test-a",
                        "part_number": 1,
                        "question_groups": [
                            {"position": 0, "display_start": 1, "display_end": 4, "question_type": 4},
                            {"position": 1, "display_start": 3, "display_end": 4, "question_type": 1},
                        ],
                    }
                ]
            }
        ),
        "utf-8",
    )

    server = QuestionBank(root).load_server_test("b10-test-a")
    first_sources = server["parts"][0]["groups"][0]["source_question_groups"]
    second_sources = server["parts"][0]["groups"][1]["source_question_groups"]

    assert [item["question_type"] for item in first_sources] == [4]
    assert [item["question_type"] for item in second_sources] == [1]


def test_single_source_range_recovers_all_questions_without_collapsing_multi_source_slots(tmp_path) -> None:
    root = tmp_path / "question-bank"
    test_dir = root / "tests"
    test_dir.mkdir(parents=True)
    test = fixture_test()
    test["parts"][0]["groups"] = [
        {
            "questions": [
                {
                    "id": f"q{number}",
                    "number": number,
                    "prompt": f"Matching prompt {number}",
                    "options": [{"value": "A", "label": "A"}],
                    "answer": "A",
                    "accepted_answers": ["A"],
                }
                for number in range(15, 22)
            ]
        },
        {
            "questions": [
                {
                    "id": f"q{number}",
                    "number": number,
                    "prompt": f"Multiple choice prompt {number}",
                    "options": [{"value": "A", "label": "A"}],
                    "answer": "A",
                    "accepted_answers": ["A"],
                }
                for number in (39, 40)
            ]
        },
    ]
    (test_dir / "b10-test-a.json").write_text(json.dumps(test), "utf-8")
    (root / "passage_source_html.local.json").write_text(
        json.dumps(
            {
                "parts": [
                    {
                        "test_id": "b10-test-a",
                        "part_number": 1,
                        "question_groups": [
                            {
                                "position": 0,
                                "display_start": 15,
                                "display_end": 15,
                                "start_index": 15,
                                "end_index": 21,
                                "question_type": 4,
                            },
                            {
                                "position": 1,
                                "display_start": 39,
                                "display_end": 39,
                                "start_index": 39,
                                "end_index": 40,
                                "question_type": 2,
                            },
                            {
                                "position": 2,
                                "display_start": 40,
                                "display_end": 40,
                                "start_index": 41,
                                "end_index": 42,
                                "question_type": 2,
                            },
                        ],
                    }
                ]
            }
        ),
        "utf-8",
    )

    public = QuestionBank(root).load_public_test("b10-test-a")
    single_source = public["parts"][0]["groups"][0]["source_question_groups"]
    multi_source = public["parts"][0]["groups"][1]["source_question_groups"]

    assert [(item["display_start"], item["display_end"]) for item in single_source] == [(15, 21)]
    assert [(item["display_start"], item["display_end"]) for item in multi_source] == [(39, 39), (40, 40)]


def test_c5_c20_use_one_renderable_ieltsbro_answer_standard() -> None:
    bank_root = Path(__file__).resolve().parents[1] / "data" / "question-bank"
    bank = QuestionBank(bank_root)
    checked_questions = 0
    bounded_choice_questions = 0

    def answer_tokens(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [item.strip() for item in re.split(r"\|\||[,|/]", str(value or "")) if item.strip()]

    for index_item in expected_test_index():
        if not 5 <= int(index_item["book_number"]) <= 20:
            continue
        server = bank.load_server_test(str(index_item["id"]))
        for part in server.get("parts") or []:
            for group in part.get("groups") or []:
                questions = group.get("questions") or []
                for question in questions:
                    checked_questions += 1
                    answer = str(question.get("answer") or "").strip()
                    accepted = [
                        str(item).strip()
                        for item in question.get("accepted_answers") or []
                        if str(item).strip()
                    ]
                    assert answer, f"{server['id']} Q{question['number']}: missing canonical answer"
                    assert accepted and accepted[0] == answer, (
                        f"{server['id']} Q{question['number']}: canonical answer and accepted standard diverged"
                    )

                for source in group.get("source_question_groups") or []:
                    allowed: set[str] = set()
                    if source.get("interaction_mode") == "matching_matrix":
                        allowed = {
                            str(option.get("index") or "").strip()
                            for option in source.get("match_options") or []
                            if str(option.get("index") or "").strip()
                        }
                    elif not source.get("questions_html") and int(source.get("question_type") or 0) in {1, 2}:
                        option_count = max(
                            (len(item.get("options") or []) for item in source.get("structured_questions") or []),
                            default=0,
                        )
                        allowed = {chr(65 + index) for index in range(option_count)}
                    elif not source.get("questions_html") and int(source.get("question_type") or 0) == 3:
                        allowed = {
                            re.sub(r"<[^>]+>", " ", str(option.get("content_html") or "")).strip()
                            for item in source.get("structured_questions") or []
                            for option in item.get("options") or []
                        }
                    if not allowed:
                        continue

                    start = int(source.get("display_start") or 0)
                    end = int(source.get("display_end") or start)
                    source_questions = questions if not start else [
                        question
                        for question in questions
                        if start <= int(question.get("display_number") or question.get("number") or 0) <= end
                    ]
                    source_questions = source_questions or questions
                    for question in source_questions:
                        bounded_choice_questions += 1
                        answer = question.get("answer")
                        assert all(token in allowed for token in answer_tokens(answer)), (
                            f"{server['id']} Q{question['number']}: {answer!r} cannot be selected from {sorted(allowed)}"
                        )

    assert checked_questions == 2080
    assert bounded_choice_questions == 1211


def test_incomplete_bank_returns_explicit_503(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QUESTION_BANK_DIR", str(tmp_path / "empty"))
    client = TestClient(app)
    status = client.get("/api/v1/question-bank/migration-status")
    assert status.status_code == 200
    assert status.json()["ready"] is False
    response = client.get("/api/v1/question-bank/tests")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "question_bank_migration_incomplete"
