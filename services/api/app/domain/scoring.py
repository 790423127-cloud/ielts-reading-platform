from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.domain.answer_evaluation import (
    evaluate_answer,
    normalize_text_answer,
    split_multi_answer,
)
from app.domain.band import attach_band_estimate

# Gap-fill tokens like $120404$ (question ids) must not leak into learner-facing copy.
_BLANK_TOKEN_RE = re.compile(r"\$\d{4,}\$")


def humanize_blank_tokens(value: Any) -> str:
    if value is None:
        return ""
    return _BLANK_TOKEN_RE.sub("_____", str(value))


def format_user_answer(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip())
    return str(value)


def _unique_multi_tokens(value: Any) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for raw_token in split_multi_answer(value):
        token = str(raw_token).strip()
        normalized = normalize_text_answer(token)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(token)
    return tokens


def _shared_multi_answer(
    questions: list[dict[str, Any]], answer_map: dict[str, Any]
) -> Any:
    """Read both current shared-array submissions and older per-slot submissions."""
    submitted = [
        answer_map.get(str(question.get("id")), "")
        for question in questions
    ]
    for value in submitted:
        if len(_unique_multi_tokens(value)) > 1:
            return value
    combined = [
        token
        for value in submitted
        for token in _unique_multi_tokens(value)
    ]
    return combined


def score_submission(
    test: dict[str, Any],
    answers: dict[str, Any],
    *,
    exam_mode: str,
    total_elapsed_seconds: int = 0,
    part_elapsed_seconds: dict[str, int] | None = None,
    question_elapsed_seconds: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Score one server-owned test without trusting any client answer key."""
    answer_map = {str(key): value for key, value in answers.items()}
    timing_map = {
        str(key): max(0, int(value or 0))
        for key, value in (question_elapsed_seconds or {}).items()
    }
    part_timing_map = {
        str(key): max(0, int(value or 0))
        for key, value in (part_elapsed_seconds or {}).items()
    }
    question_results: list[dict[str, Any]] = []
    part_results: list[dict[str, Any]] = []

    for part in test.get("parts") or []:
        part_questions: list[dict[str, Any]] = []
        for group in part.get("groups") or []:
            subtype = str(group.get("question_type") or group.get("subtype") or "other")
            question_type = str(group.get("question_label") or subtype)
            group_multi = subtype == "multiple_choice_multiple" or int(
                group.get("required_choices") or 1
            ) > 1
            questions = group.get("questions") or []
            shared_multi = bool(group.get("shared_response")) and group_multi and len(questions) > 1
            shared_answer: Any = ""
            shared_tokens: list[str] = []
            shared_correct_tokens: list[str] = []
            shared_correct_set: set[str] = set()
            shared_summary: dict[str, Any] = {}
            if shared_multi:
                shared_answer = _shared_multi_answer(questions, answer_map)
                # A shared group has a fixed number of score slots. The UI enforces
                # this limit; keep the server deterministic for malformed clients too.
                shared_tokens = _unique_multi_tokens(shared_answer)[:len(questions)]
                correct_source = questions[0].get("answer", "")
                if not str(correct_source or "").strip():
                    correct_source = questions[0].get("accepted_answers") or []
                shared_correct_tokens = _unique_multi_tokens(correct_source)
                shared_correct_set = {
                    normalize_text_answer(token) for token in shared_correct_tokens
                }
                selected_correct = [
                    token for token in shared_tokens
                    if normalize_text_answer(token) in shared_correct_set
                ]
                selected_incorrect = [
                    token for token in shared_tokens
                    if normalize_text_answer(token) not in shared_correct_set
                ]
                selected_normalized = {
                    normalize_text_answer(token) for token in shared_tokens
                }
                missed_correct = [
                    token for token in shared_correct_tokens
                    if normalize_text_answer(token) not in selected_normalized
                ]
                shared_summary = {
                    "shared_response": True,
                    "shared_response_score": len(selected_correct),
                    "shared_response_total": len(questions),
                    "selected_correct_answers": selected_correct,
                    "selected_incorrect_answers": selected_incorrect,
                    "missed_correct_answers": missed_correct,
                }

            for question_index, question in enumerate(questions):
                question_id = str(question["id"])
                user_answer = shared_answer if shared_multi else answer_map.get(question_id, "")
                accepted = question.get("accepted_answers") or [
                    question.get("answer", "")
                ]
                multi = group_multi or int(question.get("required_choices") or 1) > 1
                credited_answer = ""
                if shared_multi:
                    credited_answer = (
                        shared_tokens[question_index]
                        if question_index < len(shared_tokens)
                        else ""
                    )
                    correct = normalize_text_answer(credited_answer) in shared_correct_set
                    answer_error_type = None if correct else "incorrect"
                else:
                    correct, answer_error_type = evaluate_answer(
                        user_answer,
                        accepted,
                        subtype=subtype,
                        instructions=str(group.get("instructions") or ""),
                        multi=multi,
                    )
                evidence = question.get("evidence") or []
                if isinstance(evidence, str):
                    evidence = [evidence] if evidence.strip() else []
                row = {
                    "id": question_id,
                    "source_question_id": question.get("original_question_id") or question_id,
                    "number": question.get("display_number") or question.get("number"),
                    "original_number": question.get("number"),
                    "part_number": part.get("number"),
                    "source_part_number": part.get("source_part_number") or part.get("number"),
                    "part_title": part.get("title") or f"Part {part.get('number')}",
                    "question_type": question_type,
                    "question_subtype": subtype,
                    "question_category": group.get("question_category"),
                    "prompt": question.get("prompt") or "",
                    "instructions": group.get("instructions") or "",
                    "options": question.get("options")
                    or group.get("shared_options")
                    or group.get("options")
                    or [],
                    "user_answer": format_user_answer(user_answer),
                    "elapsed_seconds": timing_map.get(question_id, 0),
                    "correct_answer": question.get("answer", ""),
                    "is_correct": correct,
                    "answer_error_type": answer_error_type,
                    "analysis": humanize_blank_tokens(question.get("analysis") or ""),
                    "reason": humanize_blank_tokens(question.get("reason") or ""),
                    "location_analysis": humanize_blank_tokens(
                        question.get("location_analysis") or ""
                    ),
                    "paraphrasing": humanize_blank_tokens(question.get("paraphrasing") or ""),
                    "keywords": humanize_blank_tokens(question.get("keywords") or ""),
                    "evidence": [
                        humanize_blank_tokens(item) for item in evidence
                    ],
                    "evidence_available": bool(
                        evidence and any(str(item).strip() for item in evidence)
                    ),
                    "wrong_reasons": question.get("wrong_reasons"),
                    "source_test_id": part.get("source_test_id") or test.get("id"),
                }
                if shared_multi:
                    row.update(shared_summary)
                    row["credited_answer"] = credited_answer
                question_results.append(row)
                part_questions.append(row)

        part_score = sum(1 for question in part_questions if question["is_correct"])
        part_total = len(part_questions)
        part_results.append(
            {
                "part_number": part.get("number"),
                "title": part.get("title") or f"Part {part.get('number')}",
                "score": part_score,
                "total": part_total,
                "accuracy": round(part_score / part_total * 100, 1)
                if part_total
                else 0,
                "elapsed_seconds": part_timing_map.get(str(part.get("number")), 0),
            }
        )

    score = sum(1 for question in question_results if question["is_correct"])
    total = len(question_results)
    type_buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {"correct": 0, "total": 0}
    )
    for question in question_results:
        bucket = type_buckets[question["question_type"]]
        bucket["total"] += 1
        if question["is_correct"]:
            bucket["correct"] += 1

    type_results = [
        {
            "type": question_type,
            **values,
            "accuracy": round(values["correct"] / values["total"] * 100, 1)
            if values["total"]
            else 0,
        }
        for question_type, values in type_buckets.items()
    ]
    type_results.sort(key=lambda item: (item["accuracy"], -item["total"]))

    result = {
        "test_id": str(test.get("id") or ""),
        "test_title": str(test.get("title") or ""),
        "practice_mode": test.get("practice_mode") or "full_test",
        "exam_mode": exam_mode,
        "score": score,
        "total": total,
        "accuracy": round(score / total * 100, 1) if total else 0,
        "total_elapsed_seconds": max(0, int(total_elapsed_seconds or 0)),
        "part_results": part_results,
        "type_results": type_results,
        "question_results": question_results,
        "wrong_questions": [
            question for question in question_results if not question["is_correct"]
        ],
        "unanswered_count": sum(
            1
            for question in question_results
            if not str(
                question.get("credited_answer", question["user_answer"])
            ).strip()
        ),
    }
    return attach_band_estimate(result)
