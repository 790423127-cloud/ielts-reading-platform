from __future__ import annotations

import re
from typing import Any

_CODE_TOKEN_RE = re.compile(r"^[A-Za-z]{1,3}$|^[ivxlcdmIVXLCDM]+$")


def normalize_text_answer(value: str | None) -> str:
    """Normalize text without changing option-code or judgement semantics."""
    if not value:
        return ""
    text = str(value).strip().casefold()
    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,:;!?\"'")


def normalize_answer(value: str | None) -> str:
    """Normalize judgement aliases retained from the legacy scoring core."""
    text = normalize_text_answer(value)
    aliases = {
        "t": "true",
        "f": "false",
        "ng": "not given",
        "y": "yes",
        "n": "no",
    }
    return aliases.get(text, text)


_NUMBER_WORD_VALUES = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_NUMBER_TENS_VALUES = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_NUMBER_WORD_FORMS: tuple[tuple[str, str], ...] = tuple(
    sorted(
        [
            (f"{tens_word}-{unit_word}", str(tens_value + unit_value))
            for tens_word, tens_value in _NUMBER_TENS_VALUES.items()
            for unit_word, unit_value in _NUMBER_WORD_VALUES.items()
            if 1 <= unit_value <= 9
        ]
        + [
            (f"{tens_word} {unit_word}", str(tens_value + unit_value))
            for tens_word, tens_value in _NUMBER_TENS_VALUES.items()
            for unit_word, unit_value in _NUMBER_WORD_VALUES.items()
            if 1 <= unit_value <= 9
        ]
        + [(word, str(value)) for word, value in _NUMBER_WORD_VALUES.items()]
        + [(word, str(value)) for word, value in _NUMBER_TENS_VALUES.items()],
        key=lambda item: len(item[0]),
        reverse=True,
    )
)


_UNIT_ALIASES: tuple[tuple[str, str], ...] = (
    (r"\bkilometres?\b", "km"),
    (r"\bkilometers?\b", "km"),
    (r"\bkms\b", "km"),
    (r"\bmetres?\b", "m"),
    (r"\bmeters?\b", "m"),
    (r"\bcentimetres?\b", "cm"),
    (r"\bcentimeters?\b", "cm"),
    (r"\bmillimetres?\b", "mm"),
    (r"\bmillimeters?\b", "mm"),
    (r"\bkilograms?\b", "kg"),
    (r"\bkilos?\b", "kg"),
    (r"\bhours?\b", "hour"),
    (r"\bmins?\b", "minute"),
    (r"\bminutes?\b", "minute"),
)


def normalize_completion_answer(value: str | None) -> str:
    """Normalize completion/short answers for IELTS-style free text.

    Handles: case/punctuation, number words, hyphen/space variants,
    clock times (10:30 / 10.30 am), and common unit abbreviations.
    """
    text = normalize_text_answer(value)
    # half-hour == half hour
    text = re.sub(r"(?<=[a-z0-9])-(?=[a-z0-9])", " ", text)
    # 10:30 -> 10.30
    text = re.sub(r"\b(\d{1,2}):(\d{2})\b", r"\1.\2", text)
    # 10.30 am / 10.30 a.m. / 10.30pm -> 10.30 (IELTS times often omit am/pm in key)
    text = re.sub(
        r"\b(\d{1,2}\.\d{2})\s*(?:a\.?\s*m\.?|p\.?\s*m\.?)\b",
        r"\1",
        text,
    )
    text = re.sub(
        r"\b(\d{1,2})(?:a\.?\s*m\.?|p\.?\s*m\.?)\b",
        r"\1",
        text,
    )
    for pattern, replacement in _UNIT_ALIASES:
        text = re.sub(pattern, replacement, text)
    for form, digits in _NUMBER_WORD_FORMS:
        text = re.sub(
            rf"(?<![a-z-]){re.escape(form)}(?![a-z-])",
            digits,
            text,
        )
    return re.sub(r"\s+", " ", text).strip()


def _is_code_token(token: str) -> bool:
    value = str(token or "").strip()
    return bool(value and _CODE_TOKEN_RE.fullmatch(value))


def _split_multi(value: Any, *, allow_space_codes: bool = False) -> list[str]:
    """Split multi-select answers. Free text is never split on ordinary spaces."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if "||" in text:
        parts = [part.strip() for part in text.split("||") if part.strip()]
    elif "|" in text and re.fullmatch(r"[A-Za-z](\s*\|\s*[A-Za-z])+", text.replace("||", "|")):
        parts = [part.strip() for part in text.split("|") if part.strip()]
    elif "," in text:
        parts = [part.strip() for part in text.split(",") if part.strip()]
    elif "/" in text and re.fullmatch(r"[A-Za-z](\s*/\s*[A-Za-z])+", text):
        parts = [part.strip() for part in text.split("/") if part.strip()]
    elif allow_space_codes and re.search(r"\s", text):
        parts = [part for part in re.split(r"\s+", text) if part]
        if parts and all(_is_code_token(part) for part in parts):
            return parts
        return [text]
    else:
        return [text]
    return parts


def split_multi_answer(value: Any) -> list[str]:
    """Return the individual option codes from a submitted multi-select answer."""
    return _split_multi(value, allow_space_codes=True)


def is_correct_answer(user_answer: Any, accepted: list[str] | None, multi: bool = False) -> bool:
    accepted_values = [
        answer for answer in (accepted or []) if answer is not None and str(answer).strip()
    ]
    if not accepted_values:
        return False

    if multi or any("," in str(answer) or "||" in str(answer) for answer in accepted_values) or isinstance(user_answer, list):
        user_set = {
            normalize_answer(item)
            for item in _split_multi(user_answer)
            if normalize_answer(item)
        }
        if not user_set:
            return False
        for answer in accepted_values:
            accepted_set = {
                normalize_answer(item)
                for item in _split_multi(answer)
                if normalize_answer(item)
            }
            if user_set == accepted_set:
                return True
        return False

    user = normalize_answer(
        user_answer if not isinstance(user_answer, list) else ",".join(user_answer)
    )
    if not user:
        return False
    return user in {normalize_answer(answer) for answer in accepted_values}


def parse_word_limit(instructions: str | None) -> int | None:
    text = (instructions or "").casefold()
    if "one word only" in text:
        return 1
    number_words = {"one": 1, "two": 2, "three": 3, "four": 4}
    match = re.search(r"no more than\s+(one|two|three|four|\d+)\s+words?", text)
    if not match:
        return None
    token = match.group(1)
    return number_words.get(token, int(token) if token.isdigit() else None)


_ANSWER_WORD_RE = re.compile(r"[^\W\d_]+(?:[-’'][^\W\d_]+)*", re.UNICODE)
_ANSWER_NUMBER_RE = re.compile(r"(?<!\w)\d+(?:[.,:/-]\d+)*(?!\w)", re.UNICODE)


def answer_token_counts(value: Any) -> tuple[int, int]:
    if isinstance(value, list):
        counts = [answer_token_counts(item) for item in value]
        return sum(item[0] for item in counts), sum(item[1] for item in counts)
    text = str(value or "").strip()
    if not text:
        return 0, 0
    return len(_ANSWER_WORD_RE.findall(text)), len(_ANSWER_NUMBER_RE.findall(text))


def instruction_number_allowance(instructions: str | None) -> int:
    text = re.sub(r"\s+", " ", str(instructions or "").casefold())
    if re.search(r"\b(?:and\s*/\s*or|and|or)\s+(?:a|one)\s+number\b", text):
        return 1
    return 0


COMPLETION_SUBTYPES = {
    "sentence_completion",
    "summary_completion",
    "note_completion",
    "table_completion",
    "flow_chart_completion",
    "form_completion",
    "diagram_label_completion",
    "short_answer",
}


def _completion_tokens(value: Any) -> list[str]:
    text = normalize_completion_answer(
        value if not isinstance(value, list) else ",".join(str(item) for item in value)
    )
    return re.findall(r"[a-z0-9]+(?:[-'][a-z0-9]+)*", text)


def _contains_contiguous(haystack: list[str], needle: list[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(
        haystack[index : index + width] == needle
        for index in range(len(haystack) - width + 1)
    )


def completion_answer_span_error(user_answer: Any, accepted: list[str] | None) -> str:
    user_tokens = _completion_tokens(user_answer)
    if not user_tokens:
        return "incorrect"
    accepted_token_sets = [
        _completion_tokens(value)
        for value in (accepted or [])
        if str(value or "").strip()
    ]
    for correct_tokens in accepted_token_sets:
        if len(user_tokens) > len(correct_tokens) and _contains_contiguous(
            user_tokens, correct_tokens
        ):
            return "answer_span_too_long"
    for correct_tokens in accepted_token_sets:
        if len(user_tokens) < len(correct_tokens) and _contains_contiguous(
            correct_tokens, user_tokens
        ):
            return "answer_span_too_short"
    return "incorrect"


def evaluate_answer(
    user_answer: Any,
    accepted: list[str] | None,
    *,
    subtype: str,
    instructions: str,
    multi: bool = False,
) -> tuple[bool, str | None]:
    accepted_values = [
        answer for answer in (accepted or []) if answer is not None and str(answer).strip()
    ]
    if subtype in COMPLETION_SUBTYPES:
        limit = parse_word_limit(instructions)
        if limit is not None:
            words, numbers = answer_token_counts(user_answer)
            number_allowance = instruction_number_allowance(instructions)
            exceeds_limit = (
                words > limit or numbers > number_allowance
                if number_allowance
                else words + numbers > limit
            )
            if exceeds_limit:
                return False, "word_limit_exceeded"

    judgement = subtype in {"true_false_not_given", "yes_no_not_given"}
    code_choice = subtype.startswith("matching_") or subtype in {
        "multiple_choice_single",
        "multiple_choice_multiple",
    }
    space_ok = bool(multi or subtype == "multiple_choice_multiple")

    if judgement:
        correct = is_correct_answer(user_answer, accepted_values, multi=multi)
    elif code_choice or multi or isinstance(user_answer, list):
        user_parts = _split_multi(user_answer, allow_space_codes=space_ok)
        if space_ok and len(user_parts) > 1 and not all(
            _is_code_token(part) for part in user_parts
        ):
            return False, "incorrect"
        user_set = {
            normalize_text_answer(item)
            for item in user_parts
            if normalize_text_answer(item)
        }
        correct = False
        if user_set:
            candidate_sets: list[set[str]] = []
            for answer in accepted_values:
                accepted_set = {
                    normalize_text_answer(item)
                    for item in _split_multi(answer, allow_space_codes=space_ok)
                    if normalize_text_answer(item)
                }
                if accepted_set:
                    candidate_sets.append(accepted_set)
            if multi and len(accepted_values) > 1 and all(
                len(_split_multi(answer, allow_space_codes=False)) == 1
                for answer in accepted_values
            ):
                combined = {
                    normalize_text_answer(answer)
                    for answer in accepted_values
                    if normalize_text_answer(answer)
                }
                if combined:
                    candidate_sets.append(combined)
            correct = any(user_set == candidate for candidate in candidate_sets)
    else:
        user = normalize_completion_answer(
            user_answer if not isinstance(user_answer, list) else ",".join(user_answer)
        )
        accepted_normalized = {
            normalize_completion_answer(answer) for answer in accepted_values
        }
        correct = bool(user) and user in accepted_normalized

    if correct:
        return True, None
    if subtype in COMPLETION_SUBTYPES:
        return False, completion_answer_span_error(user_answer, accepted_values)
    return False, "incorrect"
