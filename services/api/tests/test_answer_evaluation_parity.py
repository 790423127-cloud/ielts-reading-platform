from __future__ import annotations

import pytest

from app.domain.answer_evaluation import evaluate_answer, normalize_completion_answer


def test_judgement_aliases_match_legacy_core() -> None:
    assert evaluate_answer("T", ["TRUE"], subtype="true_false_not_given", instructions="")[0]
    assert evaluate_answer("ng", ["NOT GIVEN"], subtype="true_false_not_given", instructions="")[0]
    assert evaluate_answer("N", ["NO"], subtype="yes_no_not_given", instructions="")[0]


def test_completion_number_words_and_figures_are_equivalent() -> None:
    assert normalize_completion_answer("twenty-one") == "21"
    assert normalize_completion_answer("twenty one") == "21"
    assert evaluate_answer(
        "twenty one",
        ["21"],
        subtype="form_completion",
        instructions="NO MORE THAN TWO WORDS AND/OR A NUMBER",
    ) == (True, None)


def test_short_answer_hyphen_time_and_unit_variants() -> None:
    # hyphen vs space
    assert evaluate_answer(
        "every half-hour",
        ["every half hour"],
        subtype="short_answer",
        instructions="NO MORE THAN THREE WORDS",
    ) == (True, None)
    # time with am/pm and colon
    assert evaluate_answer(
        "10.30 am",
        ["10.30"],
        subtype="short_answer",
        instructions="NO MORE THAN THREE WORDS AND/OR A NUMBER",
    ) == (True, None)
    assert evaluate_answer(
        "10:30",
        ["10.30"],
        subtype="short_answer",
        instructions="NO MORE THAN THREE WORDS AND/OR A NUMBER",
    ) == (True, None)
    # unit abbreviation
    assert evaluate_answer(
        "10 km",
        ["10 kilometre", "10 kilometres", "10 km"],
        subtype="short_answer",
        instructions="NO MORE THAN THREE WORDS AND/OR A NUMBER",
    ) == (True, None)


def test_free_text_is_never_split_on_spaces() -> None:
    assert evaluate_answer(
        "student accommodation",
        ["student accommodation"],
        subtype="sentence_completion",
        instructions="NO MORE THAN TWO WORDS",
    ) == (True, None)


def test_multi_choice_accepts_unordered_letter_codes() -> None:
    assert evaluate_answer(
        "D B",
        ["B", "D"],
        subtype="multiple_choice_multiple",
        instructions="Choose TWO letters",
        multi=True,
    ) == (True, None)


def test_multi_choice_does_not_accept_extra_choice() -> None:
    assert evaluate_answer(
        ["B", "D", "E"],
        ["B", "D"],
        subtype="multiple_choice_multiple",
        instructions="Choose TWO letters",
        multi=True,
    ) == (False, "incorrect")


def test_completion_word_limit_is_enforced_before_answer_membership() -> None:
    assert evaluate_answer(
        "the affordable accommodation",
        ["affordable accommodation"],
        subtype="sentence_completion",
        instructions="NO MORE THAN TWO WORDS",
    ) == (False, "word_limit_exceeded")


@pytest.mark.parametrize(
    ("user_answer", "accepted", "expected"),
    [
        ("affordable student accommodation", ["student accommodation"], "answer_span_too_long"),
        ("accommodation", ["student accommodation"], "answer_span_too_short"),
        ("transport", ["student accommodation"], "incorrect"),
    ],
)
def test_completion_span_diagnosis_matches_legacy_rules(
    user_answer: str, accepted: list[str], expected: str
) -> None:
    assert evaluate_answer(
        user_answer,
        accepted,
        subtype="sentence_completion",
        instructions="NO MORE THAN THREE WORDS",
    ) == (False, expected)
