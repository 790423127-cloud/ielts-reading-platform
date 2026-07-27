from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.domain.answer_evaluation import evaluate_answer
from app.domain.band import attach_band_estimate


def format_user_answer(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip())
    return str(value)


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
            multi = subtype == "multiple_choice_multiple" or int(
                group.get("required_choices") or 1
            ) > 1
            for question in group.get("questions") or []:
                question_id = str(question["id"])
                user_answer = answer_map.get(question_id, "")
                accepted = question.get("accepted_answers") or [
                    question.get("answer", "")
                ]
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
                    "analysis": question.get("analysis") or "",
                    "reason": question.get("reason") or "",
                    "location_analysis": question.get("location_analysis") or "",
                    "paraphrasing": question.get("paraphrasing") or "",
                    "keywords": question.get("keywords") or "",
                    "evidence": evidence,
                    "evidence_available": bool(
                        evidence and any(str(item).strip() for item in evidence)
                    ),
                    "wrong_reasons": question.get("wrong_reasons"),
                    "source_test_id": part.get("source_test_id") or test.get("id"),
                }
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
            1 for question in question_results if not str(question["user_answer"]).strip()
        ),
    }
    return attach_band_estimate(result)
