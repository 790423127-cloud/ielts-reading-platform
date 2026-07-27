from __future__ import annotations

import pytest

from app.domain.question_types import (
    EXACT_SUBTYPES,
    MC_MULTI,
    MATCH_END,
    MATCH_FEAT,
    MATCH_HEAD,
    MATCH_NAMES,
    MATCH_PLACES,
    NOTE_COMP,
    SUM_COMP,
    TABLE_COMP,
    TFNG,
    YNNG,
    classify_subtype,
    enrich_test,
)


def test_registry_contains_exactly_17_supported_subtypes() -> None:
    assert len(EXACT_SUBTYPES) == 17
    assert len(set(EXACT_SUBTYPES)) == 17


@pytest.mark.parametrize(
    ("instructions", "options", "expected"),
    [
        ("Do the following statements agree? TRUE FALSE NOT GIVEN", [], TFNG),
        ("Do the following statements agree with the views? YES NO NOT GIVEN", [], YNNG),
        ("Choose TWO letters, A-E", ["A", "B", "C", "D", "E"], MC_MULTI),
        ("Choose the correct heading for each section", ["i", "ii", "iii"], MATCH_HEAD),
        ("Complete each sentence with the correct ending", ["A", "B", "C"], MATCH_END),
        ("Which person made each statement? Match the names", ["A", "B", "C"], MATCH_NAMES),
        ("Which place contains each facility?", ["A", "B", "C", "D"], MATCH_PLACES),
        (
            "Classify the following statements as referring to A plan one B plan two C all plans.",
            ["A", "B", "C"],
            MATCH_FEAT,
        ),
        ("Complete the summary below", [], SUM_COMP),
        ("Complete the notes below", [], NOTE_COMP),
        ("Complete the table below", [], TABLE_COMP),
    ],
)
def test_classifier_keeps_legacy_subtype_semantics(instructions: str, options: list[str], expected: str) -> None:
    assert classify_subtype(instructions, {"options": options}) == expected


def test_enrichment_does_not_promote_first_questions_unique_options_to_the_whole_group() -> None:
    test = {
        "parts": [{
            "groups": [{
                "instructions": "Choose the correct letter, A, B, C or D.",
                "questions": [
                    {"id": "22", "options": [{"value": "A", "label": "floppy disk"}]},
                    {"id": "23", "options": [{"value": "A", "label": "$20"}]},
                ],
            }],
        }],
    }

    enrich_test(test)

    group = test["parts"][0]["groups"][0]
    assert "normalized_options" not in group
    assert group["questions"][0]["options"][0]["label"] == "floppy disk"
    assert group["questions"][1]["options"][0]["label"] == "$20"
