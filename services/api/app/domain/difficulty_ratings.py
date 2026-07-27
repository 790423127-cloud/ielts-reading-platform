from __future__ import annotations

"""Deterministic relative difficulty ratings for the installed GT question bank.

The source books do not publish per-test difficulty labels. These ratings use
only public passage text and question structure; answers, explanations and
learner performance are deliberately excluded.
"""

import re
from typing import Any, Iterable


_WORD_RE = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")
_SENTENCE_RE = re.compile(r"[.!?]+")
_PART_ADJUSTMENT = {1: -4.0, 2: 0.0, 3: 5.0}
_TYPE_WEIGHT = {
    "matching_headings": 1.0,
    "matching_information": 0.96,
    "multiple_choice_multiple": 0.92,
    "yes_no_not_given": 0.86,
    "true_false_not_given": 0.82,
    "matching_features": 0.8,
    "multiple_choice_single": 0.78,
    "matching_sentence_endings": 0.76,
    "matching_names": 0.76,
    "matching_places": 0.72,
    "summary_completion": 0.66,
    "diagram_label_completion": 0.62,
    "flow_chart_completion": 0.6,
    "sentence_completion": 0.52,
    "short_answer": 0.52,
    "note_completion": 0.48,
    "table_completion": 0.46,
    "other": 0.55,
}
_LABELS = {
    "easy": ("简单", "适合热身"),
    "medium": ("中等", "常规训练"),
    "hard": ("困难", "进阶挑战"),
}


def _normalise(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _part_factors(part: dict[str, Any]) -> dict[str, float]:
    text = " ".join(
        str(row.get("text") or "")
        for row in part.get("paragraphs") or []
        if isinstance(row, dict)
    )
    words = _WORD_RE.findall(text)
    sentences = [row for row in _SENTENCE_RE.split(text) if _WORD_RE.search(row)]
    word_count = len(words)
    sentence_count = max(1, len(sentences))
    long_word_count = sum(1 for word in words if len(word.replace("-", "")) >= 8)
    question_count = 0
    weighted_task_load = 0.0
    interference = 0
    for group in part.get("groups") or []:
        questions = group.get("questions") or []
        count = len(questions)
        subtype = str(group.get("question_subtype") or group.get("question_type") or "other")
        question_count += count
        weighted_task_load += _TYPE_WEIGHT.get(subtype, _TYPE_WEIGHT["other"]) * count
        if subtype in {
            "matching_headings",
            "matching_information",
            "multiple_choice_multiple",
            "yes_no_not_given",
            "true_false_not_given",
        }:
            interference += count
    question_count = max(1, question_count)
    average_sentence_words = word_count / sentence_count
    long_word_ratio = long_word_count / max(1, word_count)
    text_load = (
        0.44 * _normalise(average_sentence_words, 12.0, 27.0)
        + 0.34 * _normalise(long_word_ratio, 0.10, 0.22)
        + 0.22 * _normalise(word_count / question_count, 45.0, 95.0)
    )
    task_load = weighted_task_load / question_count
    return {
        "score": 100 * (0.57 * text_load + 0.43 * task_load)
        + _PART_ADJUSTMENT.get(int(part.get("number") or 1), 0),
        "word_count": float(word_count),
        "average_sentence_words": average_sentence_words,
        "long_word_ratio": long_word_ratio,
        "interference": float(interference),
    }


def _level(index: int, total: int) -> str:
    third = round(total / 3)
    return "easy" if index < third else "hard" if index >= total - third else "medium"


def _rating(level: str, factors: dict[str, float], index: int, total: int) -> dict[str, Any]:
    label, caption = _LABELS[level]
    if factors["interference"] >= 18:
        description = "匹配与判断题较集中，干扰信息更多"
    elif factors["average_sentence_words"] >= 21:
        description = "长句较多，跨句理解要求更高"
    elif factors["long_word_ratio"] >= 0.17:
        description = "长词与抽象表达较多，同义替换更难"
    elif level == "easy":
        description = "句子与题型负担相对较轻，适合热身"
    else:
        description = "文章与题型负担较均衡，适合常规训练"
    return {
        "level": level,
        "label": label,
        "caption": caption,
        "description": description,
        "score": round(factors["score"], 1),
        "relative_percentile": round((index + 1) / total * 100),
        "basis": {
            "word_count": int(factors["word_count"]),
            "average_sentence_words": round(factors["average_sentence_words"], 1),
            "long_word_percent": round(factors["long_word_ratio"] * 100, 1),
            "high_interference_questions": int(factors["interference"]),
        },
        "method": "relative_content_structure_v1",
        "official": False,
    }


def build_difficulty_catalog(
    tests: Iterable[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    part_rows: list[tuple[str, int, dict[str, float]]] = []
    for test in tests:
        test_id = str(test.get("id") or "")
        for part in test.get("parts") or []:
            number = int(part.get("number") or 0)
            if test_id and number:
                part_rows.append((test_id, number, _part_factors(part)))
    part_rows.sort(key=lambda row: (row[2]["score"], row[0], row[1]))
    part_ratings: dict[str, list[dict[str, Any]]] = {}
    for index, (test_id, number, factors) in enumerate(part_rows):
        part_ratings.setdefault(test_id, []).append(
            {"part_number": number, **_rating(_level(index, len(part_rows)), factors, index, len(part_rows))}
        )
    test_rows: list[tuple[str, dict[str, float]]] = []
    for test_id, ratings in part_ratings.items():
        source = [row for row in part_rows if row[0] == test_id]
        total_words = sum(row[2]["word_count"] for row in source)
        factors = {
            "score": sum(row[2]["score"] * ({1: .8, 2: 1, 3: 1.25}.get(row[1], 1)) for row in source)
            / max(1, sum({1: .8, 2: 1, 3: 1.25}.get(row[1], 1) for row in source)),
            "word_count": total_words,
            "average_sentence_words": sum(row[2]["average_sentence_words"] for row in source) / max(1, len(source)),
            "long_word_ratio": sum(row[2]["long_word_ratio"] * row[2]["word_count"] for row in source) / max(1, total_words),
            "interference": sum(row[2]["interference"] for row in source),
        }
        test_rows.append((test_id, factors))
        ratings.sort(key=lambda row: row["part_number"])
    test_rows.sort(key=lambda row: (row[1]["score"], row[0]))
    test_ratings = {
        test_id: _rating(_level(index, len(test_rows)), factors, index, len(test_rows))
        for index, (test_id, factors) in enumerate(test_rows)
    }
    return test_ratings, part_ratings
