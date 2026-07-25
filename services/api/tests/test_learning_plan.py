from __future__ import annotations

from datetime import datetime, timezone

from app.domain.learning_plan import evaluate_task_progress, target_accuracy


def _attempt(
    session_id: str,
    created_at: str,
    question_count: int,
    correct: int,
) -> dict:
    return {
        "session_id": session_id,
        "created_at": created_at,
        "question_count": question_count,
        "correct": correct,
        "accuracy": round(100 * correct / question_count, 1) if question_count else 0.0,
    }


def test_target_accuracy_is_baseline_plus_ten_bounded_to_70_90() -> None:
    assert target_accuracy(0) == 70.0
    assert target_accuracy(64) == 74.0
    assert target_accuracy(85) == 90.0
    assert target_accuracy(100) == 90.0


def test_less_than_eight_questions_cannot_qualify() -> None:
    progress = evaluate_task_progress(
        [_attempt("s1", "2026-07-01T08:00:00+00:00", 7, 7)],
        target=80,
        anchor_at="2026-07-01T00:00:00+00:00",
        now=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
    )
    assert progress["status"] == "learning"
    assert progress["distinct_success_days"] == 0
    assert progress["manual_completion_allowed"] is False
    assert progress["ai_can_mark_mastery"] is False


def test_same_day_retries_count_as_one_validation_day() -> None:
    progress = evaluate_task_progress(
        [
            _attempt("s1", "2026-07-01T08:00:00+00:00", 8, 7),
            _attempt("s2", "2026-07-01T18:00:00+00:00", 8, 8),
        ],
        target=80,
        anchor_at="2026-07-01T00:00:00+00:00",
        now=datetime(2026, 7, 1, 20, tzinfo=timezone.utc),
    )
    assert progress["status"] == "pending_validation"
    assert progress["study_day_count"] == 1
    assert progress["distinct_success_days"] == 1
    assert progress["success_streak"] == 1


def test_two_distinct_success_dates_enter_pending_review() -> None:
    progress = evaluate_task_progress(
        [
            _attempt("s1", "2026-07-01T08:00:00+00:00", 8, 7),
            _attempt("s2", "2026-07-02T08:00:00+00:00", 8, 8),
        ],
        target=80,
        anchor_at="2026-07-01T00:00:00+00:00",
        now=datetime(2026, 7, 2, 12, tzinfo=timezone.utc),
    )
    assert progress["status"] == "pending_review"
    assert progress["distinct_success_days"] == 2
    assert progress["success_streak"] == 2
    assert progress["next_review_at"] == "2026-07-04T08:00:00+00:00"


def test_review_before_due_date_does_not_mark_mastery() -> None:
    progress = evaluate_task_progress(
        [
            _attempt("s1", "2026-07-01T08:00:00+00:00", 8, 7),
            _attempt("s2", "2026-07-02T08:00:00+00:00", 8, 8),
            _attempt("s3", "2026-07-03T08:00:00+00:00", 8, 8),
        ],
        target=80,
        anchor_at="2026-07-01T00:00:00+00:00",
        now=datetime(2026, 7, 3, 12, tzinfo=timezone.utc),
    )
    assert progress["status"] == "pending_review"
    assert progress["review_successes"] == 0


def test_qualified_later_review_marks_mastery() -> None:
    progress = evaluate_task_progress(
        [
            _attempt("s1", "2026-07-01T08:00:00+00:00", 8, 7),
            _attempt("s2", "2026-07-02T08:00:00+00:00", 8, 8),
            _attempt("s3", "2026-07-05T08:00:00+00:00", 8, 7),
        ],
        target=80,
        anchor_at="2026-07-01T00:00:00+00:00",
        now=datetime(2026, 7, 5, 12, tzinfo=timezone.utc),
    )
    assert progress["status"] == "mastered"
    assert progress["review_successes"] == 1


def test_failed_later_review_reopens_training() -> None:
    progress = evaluate_task_progress(
        [
            _attempt("s1", "2026-07-01T08:00:00+00:00", 8, 7),
            _attempt("s2", "2026-07-02T08:00:00+00:00", 8, 8),
            _attempt("s3", "2026-07-05T08:00:00+00:00", 8, 5),
        ],
        target=80,
        anchor_at="2026-07-01T00:00:00+00:00",
        now=datetime(2026, 7, 5, 12, tzinfo=timezone.utc),
    )
    assert progress["status"] == "retrain"
    assert progress["review_successes"] == 0
