from __future__ import annotations

from typing import Any, Iterable

from app.repositories.session_repository import StoredSession

SKILL_LABELS = {
    "locating": "定位",
    "paraphrase": "同义替换",
    "main-detail": "主旨与细节",
    "scope-degree": "范围与程度",
    "time-cause": "时间与因果",
    "answer-boundary": "答案边界",
    "spelling-plural": "拼写和单复数",
}

COMPLETION_SUBTYPES = {
    "sentence_completion",
    "summary_completion",
    "note_completion",
    "table_completion",
    "flow_chart_completion",
    "diagram_label_completion",
    "short_answer",
}


def recommended_skill(subtype: str, answer_error_type: str | None = None) -> str:
    if answer_error_type in {"answer_span_too_long", "answer_span_too_short", "word_limit_exceeded"}:
        return "answer-boundary"
    if subtype in COMPLETION_SUBTYPES:
        return "spelling-plural" if answer_error_type == "incorrect" else "answer-boundary"
    if subtype in {"true_false_not_given", "yes_no_not_given"}:
        return "scope-degree"
    if subtype == "matching_headings":
        return "main-detail"
    if subtype.startswith("matching_"):
        return "locating"
    if subtype.startswith("multiple_choice"):
        return "paraphrase"
    return "locating"


def build_wrong_question_review(sessions: Iterable[StoredSession]) -> list[dict[str, Any]]:
    """Build deterministic unresolved wrong questions from persisted submissions.

    A wrong question remains active until it has been answered correctly twice in a
    row after the latest wrong attempt. This mirrors the legacy review rule without
    maintaining a second mutable source of truth.
    """

    states: dict[str, dict[str, Any]] = {}
    chronological = sorted(sessions, key=lambda row: row.created_at)
    for session in chronological:
        for question in session.result.get("question_results") or []:
            question_id = str(question.get("id") or "")
            if not question_id:
                continue
            state = states.setdefault(
                question_id,
                {
                    "question_id": question_id,
                    "wrong_count": 0,
                    "correct_streak_after_wrong": 0,
                    "latest_result": None,
                    "latest_wrong": None,
                    "last_attempt_at": session.created_at,
                },
            )
            is_correct = bool(question.get("is_correct"))
            state["latest_result"] = "correct" if is_correct else "wrong"
            state["last_attempt_at"] = session.created_at
            if is_correct:
                if int(state["wrong_count"]) > 0:
                    state["correct_streak_after_wrong"] = int(
                        state["correct_streak_after_wrong"]
                    ) + 1
            else:
                state["wrong_count"] = int(state["wrong_count"]) + 1
                state["correct_streak_after_wrong"] = 0
                state["latest_wrong"] = {
                    **question,
                    "source_session_id": session.id,
                    "source_test_id": session.test_id,
                    "attempted_at": session.created_at,
                }

    unresolved: list[dict[str, Any]] = []
    for state in states.values():
        if int(state["wrong_count"]) <= 0 or int(state["correct_streak_after_wrong"]) >= 2:
            continue
        question = dict(state.get("latest_wrong") or {})
        if not question:
            continue
        subtype = str(question.get("question_subtype") or "other")
        skill_id = recommended_skill(subtype, question.get("answer_error_type"))
        unresolved.append(
            {
                **question,
                "wrong_count": int(state["wrong_count"]),
                "correct_streak_after_wrong": int(state["correct_streak_after_wrong"]),
                "latest_result": state["latest_result"],
                "last_attempt_at": state["last_attempt_at"],
                "method_course_id": f"subtype-{subtype}",
                "recommended_skill_id": skill_id,
                "recommended_skill_label": SKILL_LABELS[skill_id],
                "mastery_rule": "最近一次错误后连续答对2次才移出错题库",
            }
        )
    unresolved.sort(key=lambda item: str(item.get("last_attempt_at") or ""), reverse=True)
    return unresolved
