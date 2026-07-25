from __future__ import annotations

import pytest

from app.domain.question_types import (
    EXACT_SUBTYPES,
    MC_MULTI,
    MATCH_END,
    MATCH_HEAD,
    MATCH_NAMES,
    MATCH_PLACES,
    NOTE_COMP,
    SUM_COMP,
    TABLE_COMP,
    TFNG,
    YNNG,
    classify_subtype,
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
        ("Complete the summary below", [], SUM_COMP),
        ("Complete the notes below", [], NOTE_COMP),
        ("Complete the table below", [], TABLE_COMP),
    ],
)
def test_classifier_keeps_legacy_subtype_semantics(instructions: str, options: list[str], expected: str) -> None:
    assert classify_subtype(instructions, {"options": options}) == expected
