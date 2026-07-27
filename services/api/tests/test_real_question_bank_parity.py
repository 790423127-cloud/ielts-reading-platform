from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.domain.scoring import score_submission
from app.services.question_bank import (
    ANSWER_FIELDS,
    QuestionBank,
    baseline_test_ids,
    canonical_json_bytes,
)

API_ROOT = Path(__file__).resolve().parents[1]
BANK_ROOT = API_ROOT / "data" / "question-bank"
REFERENCE_PATHS = [
    Path(__file__).parent / "fixtures" / "g4_g9_legacy_scoring_reference.json",
    Path(__file__).parent / "fixtures" / "legacy_scoring_reference.json",
]
REFERENCES = [json.loads(path.read_text("utf-8")) for path in REFERENCE_PATHS]
PARITY_CASES = [
    (test_item["id"], scenario_name, test_item["scenarios"][scenario_name])
    for reference in REFERENCES
    for test_item in reference["tests"]
    for scenario_name in reference["scenario_names"]
]

NUMBER_WORDS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "10": "ten",
    "11": "eleven",
    "12": "twelve",
    "13": "thirteen",
    "14": "fourteen",
    "15": "fifteen",
    "16": "sixteen",
    "17": "seventeen",
    "18": "eighteen",
    "19": "nineteen",
}
JUDGEMENT_ALIASES = {
    "TRUE": "T",
    "FALSE": "F",
    "NOT GIVEN": "NG",
    "YES": "Y",
    "NO": "N",
}


def _canonical(question: dict[str, Any]) -> Any:
    accepted = [
        item
        for item in (question.get("accepted_answers") or [])
        if str(item).strip()
    ]
    answer = question.get("answer")
    if answer is not None and str(answer).strip():
        return answer
    return accepted[0] if accepted else ""


def _alternate(question: dict[str, Any], subtype: str) -> Any:
    accepted = [
        item
        for item in (question.get("accepted_answers") or [])
        if str(item).strip()
    ]
    if len(accepted) > 1:
        return accepted[-1]
    answer = _canonical(question)
    text = str(answer).strip()
    upper = text.upper()
    if upper in JUDGEMENT_ALIASES:
        return JUDGEMENT_ALIASES[upper]
    if subtype == "multiple_choice_multiple":
        parts = [part.strip() for part in re.split(r"\|\||[,|/]", text) if part.strip()]
        if len(parts) > 1:
            return list(reversed(parts))
    if text in NUMBER_WORDS:
        return NUMBER_WORDS[text]
    return answer


def _build_answers(test: dict[str, Any], scenario: str) -> dict[str, Any]:
    answers: dict[str, Any] = {}
    position = 0
    for part in test.get("parts") or []:
        for group in part.get("groups") or []:
            subtype = str(group.get("question_type") or group.get("subtype") or "other")
            for question in group.get("questions") or []:
                question_id = str(question["id"])
                if scenario == "official":
                    value = _canonical(question)
                elif scenario == "blank":
                    value = ""
                else:
                    branch = position % 4
                    if branch == 0:
                        value = _canonical(question)
                    elif branch in {1, 2}:
                        value = _alternate(question, subtype)
                    else:
                        value = "__definitely_wrong__"
                answers[question_id] = value
                position += 1
    return answers


def _question_count(test: dict[str, Any]) -> int:
    return sum(
        len(group.get("questions") or [])
        for part in test.get("parts") or []
        for group in part.get("groups") or []
    )


def _assert_no_answer_fields(value: Any) -> None:
    if isinstance(value, dict):
        assert ANSWER_FIELDS.isdisjoint(value.keys())
        for child in value.values():
            _assert_no_answer_fields(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_answer_fields(child)


def _test_path(test_id: str) -> Path:
    return BANK_ROOT / "tests" / f"{test_id}.json"


def test_declared_manifest_is_consistent_and_all_available_files_match_hashes() -> None:
    manifest = json.loads((BANK_ROOT / "migration_manifest.json").read_text("utf-8"))
    index = json.loads((BANK_ROOT / "test_index.json").read_text("utf-8"))

    assert len(index) == 58
    assert len(manifest["tests"]) == 58
    assert manifest["total_questions"] == 2320
    assert [item["id"] for item in index] == [item["id"] for item in manifest["tests"]]

    available = [item for item in manifest["tests"] if _test_path(item["id"]).is_file()]
    available_ids = {str(item["id"]) for item in available}
    assert baseline_test_ids() <= available_ids

    total_questions = 0
    for item in available:
        raw = canonical_json_bytes(_test_path(item["id"]).read_bytes())
        assert len(raw) == item["bytes"]
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        test = json.loads(raw.decode("utf-8"))
        assert test["id"] == item["id"]
        assert _question_count(test) == 40
        total_questions += 40

    assert total_questions == len(available) * 40


def test_all_available_public_tests_strip_answers_and_explanations() -> None:
    bank = QuestionBank(BANK_ROOT)
    status = bank.migration_status()
    available = bank.index()
    assert status["found_tests"] == len(available)
    assert status["found_questions"] == len(available) * 40
    assert status["baseline_ready"] is True
    assert status["ready"] is (len(available) == 58)
    for index_item in available:
        public_test = bank.load_public_test(index_item["id"])
        assert _question_count(public_test) == 40
        _assert_no_answer_fields(public_test)


def test_g4_g9_verified_source_repairs_are_preserved_when_extension_is_installed() -> None:
    if not _test_path("b4-test-a").is_file() or not _test_path("b8-test-b").is_file():
        pytest.skip("公共干净检出不包含剑雅4–9私有扩展题库")
    bank = QuestionBank(BANK_ROOT)
    b4 = bank.load_server_test("b4-test-a")
    b4_group = next(
        group
        for part in b4["parts"]
        for group in part["groups"]
        if str(group.get("id")) == "16199"
    )
    assert b4_group["shared_response"] is True
    assert b4_group["shared_response_numbers"] == [28, 29, 30]
    assert {
        question["answer"]
        for question in b4_group["questions"]
    } == {"A,D,F"}

    b8 = bank.load_server_test("b8-test-b")
    b8_questions = {
        int(question["number"]): question
        for part in b8["parts"]
        for group in part["groups"]
        for question in group["questions"]
    }
    assert max(b8_questions) == 40
    assert b8_questions[39]["answer"] == "A,C"
    assert b8_questions[40]["answer"] == "B,F"


@pytest.mark.parametrize(
    ("test_id", "scenario", "expected"),
    PARITY_CASES,
    ids=[f"{test_id}-{scenario}" for test_id, scenario, _ in PARITY_CASES],
)
def test_new_scoring_matches_legacy_on_real_tests(
    test_id: str,
    scenario: str,
    expected: dict[str, Any],
) -> None:
    if not _test_path(test_id).is_file():
        pytest.skip(f"私有扩展题库未安装：{test_id}")
    bank = QuestionBank(BANK_ROOT)
    test = bank.load_server_test(test_id)
    answers = _build_answers(test, scenario)
    result = score_submission(
        test,
        answers,
        exam_mode="mock_exam",
        total_elapsed_seconds=0,
    )

    assert result["score"] == expected["score"]
    assert result["total"] == expected["total"] == 40
    assert result.get("estimated_gt_reading_band") == expected["estimated_band"]
    assert [
        {
            "part_number": row["part_number"],
            "score": row["score"],
            "total": row["total"],
        }
        for row in result["part_results"]
    ] == expected["part_scores"]
    assert [
        {
            "id": row["id"],
            "is_correct": row["is_correct"],
            "answer_error_type": row.get("answer_error_type"),
        }
        for row in result["question_results"]
    ] == expected["question_results"]
