from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

from app.repositories.learning_plan_repository import LearningPlanRepository
from app.repositories.session_repository import StoredSession


def _questions(*, count: int, correct: int, subtype: str = "true_false_not_given") -> list[dict]:
    return [
        {
            "id": f"q-{index + 1}",
            "number": index + 1,
            "part_number": 1,
            "question_type": "判断题",
            "question_subtype": subtype,
            "prompt": f"Question {index + 1}",
            "user_answer": "TRUE" if index < correct else "FALSE",
            "correct_answer": "TRUE",
            "is_correct": index < correct,
            "answer_error_type": None if index < correct else "incorrect",
            "evidence": ["Verified evidence."],
        }
        for index in range(count)
    ]


def _session(
    session_id: str,
    created_at: str,
    *,
    count: int = 8,
    correct: int = 8,
    skill_id: str | None = "scope-degree",
) -> StoredSession:
    result = {
        "test_id": f"ability-{skill_id}" if skill_id else "b10-test-a",
        "test_title": "能力训练",
        "question_results": _questions(count=count, correct=correct),
    }
    if skill_id:
        result["skill_id"] = skill_id
    return StoredSession(
        id=session_id,
        user_id="owner",
        client_submission_id=f"client-{session_id}",
        test_id=str(result["test_id"]),
        result=result,
        created_at=created_at,
        idempotent_replay=False,
    )


def _count(db_path, table: str) -> int:
    with sqlite3.connect(db_path) as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_repository_builds_one_stable_task_and_review_from_sessions(tmp_path) -> None:
    database = tmp_path / "plan.sqlite3"
    repository = LearningPlanRepository(database)
    sessions = [
        _session("wrong", "2026-07-01T08:00:00+00:00", correct=7),
        _session("success-day-1", "2026-07-02T08:00:00+00:00", correct=8),
        _session("success-day-2", "2026-07-03T08:00:00+00:00", correct=8),
    ]

    first = repository.synchronize(
        user_id="owner",
        sessions=sessions,
        now=datetime(2026, 7, 3, 12, tzinfo=timezone.utc),
    )
    assert first["active_task_count"] == 1
    task = first["tasks"][0]
    assert task["skill_key"] == "scope-degree"
    assert task["minimum_questions"] == 8
    assert task["required_success_days"] == 2
    assert task["status"] == "pending_review"
    assert task["success_streak"] == 2
    assert task["distinct_success_days"] == 2
    assert task["recommended_course_id"] == "subtype-true_false_not_given"
    assert first["review_schedule"][0]["status"] == "scheduled"

    second = repository.synchronize(
        user_id="owner",
        sessions=sessions,
        now=datetime(2026, 7, 3, 13, tzinfo=timezone.utc),
    )
    assert second["tasks"][0]["id"] == task["id"]
    assert _count(database, "learning_tasks") == 1
    assert _count(database, "task_attempts") == 3
    assert _count(database, "review_schedule") == 1
    assert _count(database, "skill_mastery") == 1


def test_later_review_marks_mastery_and_new_wrong_reopens_task(tmp_path) -> None:
    database = tmp_path / "plan-reset.sqlite3"
    repository = LearningPlanRepository(database)
    mastered_sessions = [
        _session("wrong", "2026-07-01T08:00:00+00:00", correct=7),
        _session("success-day-1", "2026-07-02T08:00:00+00:00", correct=8),
        _session("success-day-2", "2026-07-03T08:00:00+00:00", correct=8),
        _session("later-review", "2026-07-07T08:00:00+00:00", correct=8),
    ]
    mastered = repository.synchronize(
        user_id="owner",
        sessions=mastered_sessions,
        now=datetime(2026, 7, 7, 12, tzinfo=timezone.utc),
    )
    assert mastered["tasks"][0]["status"] == "mastered"
    assert mastered["mastered_skill_count"] == 1
    assert mastered["review_schedule"][0]["status"] == "completed"

    reopened_sessions = [
        *mastered_sessions,
        _session("new-wrong", "2026-07-08T08:00:00+00:00", correct=6),
    ]
    reopened = repository.synchronize(
        user_id="owner",
        sessions=reopened_sessions,
        now=datetime(2026, 7, 8, 12, tzinfo=timezone.utc),
    )
    task = reopened["tasks"][0]
    assert task["source_session_id"] == "new-wrong"
    assert task["source_wrong_at"] == "2026-07-08T08:00:00+00:00"
    assert task["status"] == "retrain"
    assert task["success_streak"] == 0
    assert task["distinct_success_days"] == 0
    assert reopened["mastered_skill_count"] == 0
    assert reopened["review_schedule"] == []


def test_users_have_isolated_tasks_and_mastery(tmp_path) -> None:
    database = tmp_path / "plan-users.sqlite3"
    repository = LearningPlanRepository(database)
    owner_sessions = [_session("owner-wrong", "2026-07-01T08:00:00+00:00", correct=5)]

    owner = repository.synchronize(
        user_id="owner",
        sessions=owner_sessions,
        now=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
    )
    other = repository.synchronize(
        user_id="other",
        sessions=[],
        now=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
    )
    assert owner["active_task_count"] == 1
    assert other["active_task_count"] == 0
    assert other["tasks"] == []
