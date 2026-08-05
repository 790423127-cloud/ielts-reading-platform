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
PROTECTED_BRAND_NAMES = {"interexchange"}
KNOWN_OCR_TOKENS = re.compile(
    r"\b(?:lt|lf|lnterfxchange|interfxchange|Interfxchange|lUCN|lAM|"
    r"LAM Roadsmart|cormpany|madeon|probablygive|willstill|ClimbingWall|inthe|"
    r"statemcnt)\b",
)
KNOWN_MISSING_SPACE_BOUNDARIES = re.compile(
    r"[A-Za-z][.!?][A-Z]|[A-Za-z],[A-Za-z]|[A-Za-z];[A-Za-z]|[A-Za-z]:[A-Za-z]"
)


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_strings(child)


def _public_exam_strings(test: dict[str, Any]):
    for part in test.get("parts") or []:
        yield str(part.get("article_title") or "")
        for paragraph in part.get("paragraphs") or []:
            yield str(paragraph.get("text") or "")
        for group in part.get("groups") or []:
            yield str(group.get("instructions") or "")
            yield str(group.get("content_template") or "")
            for option in group.get("normalized_options") or []:
                yield str(option.get("label") or "")
            for question in group.get("questions") or []:
                yield str(question.get("prompt") or "")
                for option in question.get("options") or []:
                    yield str(option.get("label") or "")


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[right_index] + 1,
                previous[right_index - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


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
            questions = group.get("questions") or []
            if scenario == "mixed" and group.get("shared_response") and len(questions) > 1:
                canonical_parts = [
                    part.strip()
                    for part in re.split(r"\|\||[,|/]", str(_canonical(questions[0])))
                    if part.strip()
                ]
                shared_value = [
                    "__definitely_wrong__"
                    if (position + offset) % 4 == 3
                    else canonical_parts[offset % len(canonical_parts)]
                    for offset in range(len(questions))
                ]
                for question in questions:
                    answers[str(question["id"])] = shared_value
                position += len(questions)
                continue
            for question in questions:
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


def test_protected_brand_names_have_no_near_match_ocr_variants() -> None:
    suspicious: list[str] = []
    for path in sorted((BANK_ROOT / "tests").glob("*.json")):
        payload = json.loads(path.read_text("utf-8"))
        for text in _iter_strings(payload):
            for token in re.findall(r"[A-Za-z]+", text):
                normalized = token.lower()
                for brand in PROTECTED_BRAND_NAMES:
                    if (
                        normalized != brand
                        and abs(len(normalized) - len(brand)) <= 2
                        and _edit_distance(normalized, brand) <= 2
                    ):
                        suspicious.append(f"{path.name}: {token} -> {brand}")
    assert suspicious == []


def test_all_question_bank_copy_has_no_known_ocr_tokens() -> None:
    suspicious: list[str] = []
    for path in sorted((BANK_ROOT / "tests").glob("*.json")):
        payload = json.loads(path.read_text("utf-8"))
        for text in _iter_strings(payload):
            match = KNOWN_OCR_TOKENS.search(text)
            if match:
                suspicious.append(f"{path.name}: {match.group(0)}")
    assert suspicious == []


def test_public_exam_copy_has_no_joined_punctuation_boundaries() -> None:
    suspicious: list[str] = []
    for path in sorted((BANK_ROOT / "tests").glob("*.json")):
        payload = json.loads(path.read_text("utf-8"))
        for text in _public_exam_strings(payload):
            without_initialisms = re.sub(r"\b(?:[A-Z]\.){2,}[A-Z]?\.?", "", text)
            match = KNOWN_MISSING_SPACE_BOUNDARIES.search(without_initialisms)
            if match:
                suspicious.append(f"{path.name}: {match.group(0)}")
    assert suspicious == []


def test_verified_numeric_ocr_repairs_are_preserved() -> None:
    b5 = json.loads(_test_path("b5-test-a").read_text("utf-8"))
    b5_copy = "\n".join(_iter_strings(b5))
    assert "clothes worth $80 in August" in b5_copy
    assert "clothes worth S80 in August" not in b5_copy

    b9 = json.loads(_test_path("b9-test-a").read_text("utf-8"))
    b9_copy = "\n".join(_iter_strings(b9))
    assert "01480 88056" in b9_copy
    assert "O1480 88056" not in b9_copy

    b19 = json.loads(_test_path("b19-test-1").read_text("utf-8"))
    b19_copy = "\n".join(_iter_strings(b19))
    assert "£8 on-board fine" in b19_copy
    assert "f8 on-board fine" not in b19_copy


def test_reading_passage_references_match_their_part_context() -> None:
    mismatches: list[str] = []
    for path in sorted((BANK_ROOT / "tests").glob("*.json")):
        payload = json.loads(path.read_text("utf-8"))
        for part in payload["parts"]:
            expected = str(part["number"])
            for group in part["groups"]:
                instructions = str(group.get("instructions") or "")
                match = re.search(r"Reading Passage\s*(\d+)", instructions, re.IGNORECASE)
                if match and match.group(1) != expected:
                    mismatches.append(
                        f"{path.name}: group {group.get('id')} references "
                        f"Passage {match.group(1)} inside Part {expected}"
                    )
    assert mismatches == []


def test_b5_work_travel_judgement_instructions_keep_the_source_context() -> None:
    b5 = json.loads(_test_path("b5-test-a").read_text("utf-8"))
    group = next(
        group
        for part in b5["parts"]
        for group in part["groups"]
        if str(group.get("id")) == "16146"
    )
    instructions = group["instructions"]
    assert "the advertisement on the previous page" in instructions
    assert "In boxes 15-20 on your answer sheet, write" in instructions
    assert "Reading Passage 2" not in instructions


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
