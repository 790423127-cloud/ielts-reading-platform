from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

VERSION = "0.6.0"
MINIMUM_QUESTIONS = 8
REQUIRED_SUCCESS_DAYS = 2
# 达标当天按第1天计算，因此“第3天复习”需要间隔2个自然日。
REVIEW_DELAY_DAYS = 2

STATUS_LABELS = {
    "not_started": "未开始",
    "learning": "学习中",
    "pending_validation": "待验证",
    "pending_review": "待复习",
    "mastered": "已掌握",
    "retrain": "需要重新训练",
}


def parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def target_accuracy(baseline: Any) -> float:
    try:
        numeric = float(baseline or 0)
    except (TypeError, ValueError):
        numeric = 0.0
    return float(min(90, max(70, round(numeric + 10))))


def collapse_daily_attempts(
    attempt_rows: Iterable[dict[str, Any]],
    *,
    target: float,
    minimum_questions: int = MINIMUM_QUESTIONS,
) -> list[dict[str, Any]]:
    grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()
    ordered = sorted(
        (dict(row) for row in attempt_rows),
        key=lambda row: str(row.get("created_at") or ""),
    )
    for row in ordered:
        parsed = parse_datetime(row.get("created_at"))
        if not parsed:
            continue
        day = parsed.date().isoformat()
        question_count = int(row.get("question_count") or 0)
        correct = int(row.get("correct") or 0)
        accuracy = float(row.get("accuracy") or 0)
        qualified = question_count >= minimum_questions and accuracy >= target
        current = grouped.setdefault(
            day,
            {
                "date": day,
                "created_at": iso(parsed),
                "question_count": 0,
                "correct": 0,
                "accuracy": 0.0,
                "qualified": False,
                "session_ids": [],
            },
        )
        current["question_count"] = question_count
        current["correct"] = correct
        current["accuracy"] = accuracy
        current["qualified"] = bool(current["qualified"] or qualified)
        current["created_at"] = iso(parsed)
        if row.get("session_id"):
            current["session_ids"].append(str(row["session_id"]))
    return list(grouped.values())


def evaluate_task_progress(
    attempt_rows: Iterable[dict[str, Any]],
    *,
    target: float,
    anchor_at: Any,
    now: datetime | None = None,
    minimum_questions: int = MINIMUM_QUESTIONS,
    required_success_days: int = REQUIRED_SUCCESS_DAYS,
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    anchor = parse_datetime(anchor_at) or datetime.min.replace(tzinfo=timezone.utc)
    rows = [
        dict(row)
        for row in attempt_rows
        if (parse_datetime(row.get("created_at")) or anchor) >= anchor
    ]
    days = collapse_daily_attempts(
        rows,
        target=target,
        minimum_questions=minimum_questions,
    )
    streak = 0
    completion_day: dict[str, Any] | None = None
    for day in days:
        streak = streak + 1 if day["qualified"] else 0
        if streak >= required_success_days and completion_day is None:
            completion_day = day
    latest = days[-1] if days else None
    qualified_days = [day for day in days if day["qualified"]]

    if not days:
        status = "not_started"
    elif completion_day is None:
        if streak == 1:
            status = "pending_validation"
        elif int(latest.get("question_count") or 0) < minimum_questions:
            status = "learning"
        else:
            status = "retrain"
    else:
        completed_at = parse_datetime(completion_day["created_at"]) or now
        due_at = completed_at + timedelta(days=REVIEW_DELAY_DAYS)
        review_days = [
            day
            for day in days
            if (parse_datetime(day.get("created_at")) or completed_at) >= due_at
        ]
        if not review_days:
            status = "pending_review"
        elif review_days[-1]["qualified"]:
            status = "mastered"
        else:
            status = "retrain"
    completed_at_iso = (
        str(completion_day.get("created_at")) if completion_day else None
    )
    next_review_at = None
    if completion_day:
        completion_time = parse_datetime(completion_day["created_at"])
        if completion_time:
            next_review_at = iso(completion_time + timedelta(days=REVIEW_DELAY_DAYS))

    return {
        "status": status,
        "status_label": STATUS_LABELS[status],
        "study_day_count": len(days),
        "distinct_success_days": len(qualified_days),
        "success_streak": streak,
        "required_success_days": required_success_days,
        "minimum_questions": minimum_questions,
        "target_accuracy": float(target),
        "current_question_count": int((latest or {}).get("question_count") or 0),
        "recent_accuracy": float((latest or {}).get("accuracy") or 0),
        "last_attempt_date": str((latest or {}).get("date") or ""),
        "completed_at": completed_at_iso,
        "next_review_at": next_review_at,
        "review_successes": 1 if status == "mastered" else 0,
        "manual_completion_allowed": False,
        "ai_can_mark_mastery": False,
    }


def build_plan_summary(
    tasks: Iterable[dict[str, Any]],
    mastery: Iterable[dict[str, Any]],
    reviews: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    task_rows = [dict(row) for row in tasks]
    mastery_rows = [dict(row) for row in mastery]
    review_rows = [dict(row) for row in reviews]
    priority_order = {
        "retrain": 0,
        "pending_review": 1,
        "pending_validation": 2,
        "learning": 3,
        "not_started": 4,
        "mastered": 5,
    }
    task_rows.sort(
        key=lambda row: (
            priority_order.get(str(row.get("status")), 9),
            -int(row.get("wrong_count") or 0),
            str(row.get("updated_at") or ""),
        )
    )
    due_reviews = [
        row
        for row in review_rows
        if row.get("status") in {"due", "retry"}
    ]
    return {
        "version": VERSION,
        "policy": {
            "minimum_questions": MINIMUM_QUESTIONS,
            "required_success_days": REQUIRED_SUCCESS_DAYS,
            "review_delay_days": REVIEW_DELAY_DAYS,
            "later_review_required": True,
            "manual_completion_allowed": False,
            "ai_can_mark_mastery": False,
        },
        "tasks": task_rows,
        "active_tasks": [row for row in task_rows if row.get("status") != "mastered"],
        "mastered_tasks": [row for row in task_rows if row.get("status") == "mastered"],
        "skill_mastery": mastery_rows,
        "review_schedule": review_rows,
        "due_reviews": due_reviews,
        "active_task_count": sum(1 for row in task_rows if row.get("status") != "mastered"),
        "mastered_skill_count": sum(1 for row in mastery_rows if row.get("status") == "mastered"),
        "due_review_count": len(due_reviews),
    }
