from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from app.domain.learning_plan import (
    MINIMUM_QUESTIONS,
    STATUS_LABELS,
    build_plan_summary,
    evaluate_task_progress,
    iso,
    parse_datetime,
    target_accuracy,
)
from app.domain.review import SKILL_LABELS, recommended_skill
from app.repositories.session_repository import StoredSession


class LearningPlanRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS learning_tasks (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    skill_key TEXT NOT NULL,
                    skill_label TEXT NOT NULL,
                    question_subtype TEXT,
                    reason_code TEXT,
                    source_session_id TEXT,
                    source_question_id TEXT,
                    source_wrong_at TEXT NOT NULL,
                    recommended_course_id TEXT,
                    minimum_questions INTEGER NOT NULL DEFAULT 8,
                    target_accuracy REAL NOT NULL DEFAULT 80,
                    required_success_days INTEGER NOT NULL DEFAULT 2,
                    wrong_count INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'not_started',
                    status_label TEXT NOT NULL DEFAULT '未开始',
                    current_question_count INTEGER NOT NULL DEFAULT 0,
                    recent_accuracy REAL NOT NULL DEFAULT 0,
                    success_streak INTEGER NOT NULL DEFAULT 0,
                    distinct_success_days INTEGER NOT NULL DEFAULT 0,
                    next_review_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, skill_key)
                );
                CREATE INDEX IF NOT EXISTS idx_learning_tasks_user_status
                    ON learning_tasks(user_id, status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS task_attempts (
                    task_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    question_count INTEGER NOT NULL,
                    correct INTEGER NOT NULL,
                    accuracy REAL NOT NULL,
                    qualified INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(task_id, session_id)
                );

                CREATE TABLE IF NOT EXISTS review_schedule (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    skill_key TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_session_id TEXT,
                    completed_session_id TEXT,
                    completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, task_id)
                );
                CREATE INDEX IF NOT EXISTS idx_review_schedule_user_due
                    ON review_schedule(user_id, status, due_at);

                CREATE TABLE IF NOT EXISTS skill_mastery (
                    user_id TEXT NOT NULL,
                    skill_key TEXT NOT NULL,
                    skill_label TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    correct INTEGER NOT NULL DEFAULT 0,
                    recent_accuracy REAL NOT NULL DEFAULT 0,
                    weighted_accuracy REAL NOT NULL DEFAULT 0,
                    target_hit_streak INTEGER NOT NULL DEFAULT 0,
                    review_successes INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'not_started',
                    status_label TEXT NOT NULL DEFAULT '未开始',
                    last_practised_at TEXT,
                    next_review_at TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, skill_key)
                );
                """
            )
            connection.commit()

    @staticmethod
    def _task_id(user_id: str, skill_key: str) -> str:
        digest = hashlib.sha256(f"{user_id}:{skill_key}".encode("utf-8")).hexdigest()[:24]
        return f"task-{digest}"

    @staticmethod
    def _review_id(user_id: str, skill_key: str) -> str:
        digest = hashlib.sha256(f"review:{user_id}:{skill_key}".encode("utf-8")).hexdigest()[:24]
        return f"review-{digest}"

    @staticmethod
    def _session_skill_rows(
        sessions: Iterable[StoredSession],
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        attempts: list[dict[str, Any]] = []
        latest_wrong: dict[str, dict[str, Any]] = {}
        totals: dict[str, dict[str, Any]] = {}
        for session in sorted(sessions, key=lambda row: row.created_at):
            result = session.result
            forced_skill = str(result.get("skill_id") or "").strip()
            buckets: dict[str, dict[str, Any]] = {}
            for question in result.get("question_results") or []:
                subtype = str(question.get("question_subtype") or "other")
                error_type = question.get("answer_error_type") if not question.get("is_correct") else None
                skill_key = forced_skill or recommended_skill(subtype, error_type)
                bucket = buckets.setdefault(
                    skill_key,
                    {
                        "session_id": session.id,
                        "skill_key": skill_key,
                        "question_count": 0,
                        "correct": 0,
                        "created_at": session.created_at,
                    },
                )
                bucket["question_count"] += 1
                if question.get("is_correct"):
                    bucket["correct"] += 1
                else:
                    current = latest_wrong.get(skill_key)
                    latest = {
                        "skill_key": skill_key,
                        "skill_label": SKILL_LABELS.get(skill_key, skill_key),
                        "question_subtype": subtype,
                        "reason_code": str(error_type or "incorrect"),
                        "source_session_id": session.id,
                        "source_question_id": str(question.get("id") or ""),
                        "source_wrong_at": session.created_at,
                        "recommended_course_id": f"subtype-{subtype}",
                        "wrong_count": int((current or {}).get("wrong_count") or 0) + 1,
                    }
                    latest_wrong[skill_key] = latest
            for bucket in buckets.values():
                count = int(bucket["question_count"])
                correct = int(bucket["correct"])
                bucket["accuracy"] = round(100 * correct / count, 1) if count else 0.0
                attempts.append(bucket)
                total = totals.setdefault(
                    bucket["skill_key"],
                    {
                        "attempts": 0,
                        "correct": 0,
                        "last_practised_at": session.created_at,
                        "latest_accuracy": 0.0,
                    },
                )
                total["attempts"] += count
                total["correct"] += correct
                total["last_practised_at"] = session.created_at
                total["latest_accuracy"] = bucket["accuracy"]
        return attempts, latest_wrong, totals

    def synchronize(
        self,
        *,
        user_id: str,
        sessions: Iterable[StoredSession],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        now_iso = iso(now)
        attempts, latest_wrong, totals = self._session_skill_rows(sessions)

        with self._connect() as connection:
            for skill_key, source in latest_wrong.items():
                task_id = self._task_id(user_id, skill_key)
                skill_attempts_all = [row for row in attempts if row["skill_key"] == skill_key]
                total_row = totals.get(skill_key) or {}
                baseline = (
                    round(
                        100
                        * int(total_row.get("correct") or 0)
                        / max(1, int(total_row.get("attempts") or 0)),
                        1,
                    )
                )
                target = target_accuracy(baseline)
                connection.execute(
                    """
                    INSERT INTO learning_tasks (
                        id, user_id, skill_key, skill_label, question_subtype,
                        reason_code, source_session_id, source_question_id,
                        source_wrong_at, recommended_course_id, minimum_questions,
                        target_accuracy, required_success_days, wrong_count,
                        status, status_label, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 8, ?, 2, ?, 'not_started', '未开始', ?, ?)
                    ON CONFLICT(user_id, skill_key) DO UPDATE SET
                        skill_label = excluded.skill_label,
                        question_subtype = excluded.question_subtype,
                        reason_code = excluded.reason_code,
                        source_session_id = excluded.source_session_id,
                        source_question_id = excluded.source_question_id,
                        source_wrong_at = excluded.source_wrong_at,
                        recommended_course_id = excluded.recommended_course_id,
                        target_accuracy = excluded.target_accuracy,
                        wrong_count = excluded.wrong_count,
                        updated_at = excluded.updated_at
                    """,
                    (
                        task_id,
                        user_id,
                        skill_key,
                        source["skill_label"],
                        source["question_subtype"],
                        source["reason_code"],
                        source["source_session_id"],
                        source["source_question_id"],
                        source["source_wrong_at"],
                        source["recommended_course_id"],
                        target,
                        source["wrong_count"],
                        source["source_wrong_at"],
                        now_iso,
                    ),
                )
                connection.execute("DELETE FROM task_attempts WHERE task_id = ?", (task_id,))
                anchor = parse_datetime(source["source_wrong_at"]) or datetime.min.replace(tzinfo=timezone.utc)
                for row in skill_attempts_all:
                    created = parse_datetime(row["created_at"])
                    if not created or created < anchor:
                        continue
                    qualified = int(
                        int(row["question_count"]) >= MINIMUM_QUESTIONS
                        and float(row["accuracy"]) >= target
                    )
                    connection.execute(
                        """
                        INSERT INTO task_attempts (
                            task_id, session_id, question_count, correct,
                            accuracy, qualified, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            task_id,
                            row["session_id"],
                            row["question_count"],
                            row["correct"],
                            row["accuracy"],
                            qualified,
                            row["created_at"],
                        ),
                    )
                task_attempts = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM task_attempts WHERE task_id = ? ORDER BY created_at, session_id",
                        (task_id,),
                    ).fetchall()
                ]
                progress = evaluate_task_progress(
                    task_attempts,
                    target=target,
                    anchor_at=source["source_wrong_at"],
                    now=now,
                )
                connection.execute(
                    """
                    UPDATE learning_tasks SET
                        status = ?, status_label = ?, current_question_count = ?,
                        recent_accuracy = ?, success_streak = ?,
                        distinct_success_days = ?, next_review_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        progress["status"],
                        progress["status_label"],
                        progress["current_question_count"],
                        progress["recent_accuracy"],
                        progress["success_streak"],
                        progress["distinct_success_days"],
                        progress["next_review_at"],
                        now_iso,
                        task_id,
                    ),
                )

                if progress["next_review_at"]:
                    due = parse_datetime(progress["next_review_at"]) or now
                    if progress["status"] == "mastered":
                        review_status = "completed"
                    elif progress["status"] == "retrain" and now >= due:
                        review_status = "retry"
                    elif now >= due:
                        review_status = "due"
                    else:
                        review_status = "scheduled"
                    review_id = self._review_id(user_id, skill_key)
                    completion_session = None
                    if progress["status"] == "mastered" and task_attempts:
                        completion_session = task_attempts[-1]["session_id"]
                    connection.execute(
                        """
                        INSERT INTO review_schedule (
                            id, user_id, task_id, skill_key, due_at, status,
                            source_session_id, completed_session_id, completed_at,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id, task_id) DO UPDATE SET
                            due_at = excluded.due_at,
                            status = excluded.status,
                            source_session_id = excluded.source_session_id,
                            completed_session_id = excluded.completed_session_id,
                            completed_at = excluded.completed_at,
                            updated_at = excluded.updated_at
                        """,
                        (
                            review_id,
                            user_id,
                            task_id,
                            skill_key,
                            progress["next_review_at"],
                            review_status,
                            source["source_session_id"],
                            completion_session,
                            now_iso if review_status == "completed" else None,
                            now_iso,
                            now_iso,
                        ),
                    )
                else:
                    connection.execute(
                        "DELETE FROM review_schedule WHERE user_id = ? AND task_id = ?",
                        (user_id, task_id),
                    )

            for skill_key, total in totals.items():
                task = connection.execute(
                    "SELECT * FROM learning_tasks WHERE user_id = ? AND skill_key = ?",
                    (user_id, skill_key),
                ).fetchone()
                attempt_count = int(total.get("attempts") or 0)
                correct_count = int(total.get("correct") or 0)
                weighted = round(100 * correct_count / max(1, attempt_count), 1)
                status = str(task["status"]) if task else ("learning" if attempt_count >= 8 else "not_started")
                next_review_at = task["next_review_at"] if task else None
                review_successes = 1 if status == "mastered" else 0
                connection.execute(
                    """
                    INSERT INTO skill_mastery (
                        user_id, skill_key, skill_label, attempts, correct,
                        recent_accuracy, weighted_accuracy, target_hit_streak,
                        review_successes, status, status_label,
                        last_practised_at, next_review_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, skill_key) DO UPDATE SET
                        skill_label = excluded.skill_label,
                        attempts = excluded.attempts,
                        correct = excluded.correct,
                        recent_accuracy = excluded.recent_accuracy,
                        weighted_accuracy = excluded.weighted_accuracy,
                        target_hit_streak = excluded.target_hit_streak,
                        review_successes = excluded.review_successes,
                        status = excluded.status,
                        status_label = excluded.status_label,
                        last_practised_at = excluded.last_practised_at,
                        next_review_at = excluded.next_review_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        user_id,
                        skill_key,
                        SKILL_LABELS.get(skill_key, skill_key),
                        attempt_count,
                        correct_count,
                        float(total.get("latest_accuracy") or 0),
                        weighted,
                        int(task["success_streak"] or 0) if task else 0,
                        review_successes,
                        status,
                        STATUS_LABELS.get(status, status),
                        total.get("last_practised_at"),
                        next_review_at,
                        now_iso,
                    ),
                )
            connection.commit()
        return self.snapshot(user_id=user_id)

    def snapshot(self, *, user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            tasks = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM learning_tasks WHERE user_id = ? ORDER BY updated_at DESC, id",
                    (user_id,),
                ).fetchall()
            ]
            mastery = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM skill_mastery WHERE user_id = ? ORDER BY weighted_accuracy, skill_key",
                    (user_id,),
                ).fetchall()
            ]
            reviews = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM review_schedule WHERE user_id = ? ORDER BY due_at, id",
                    (user_id,),
                ).fetchall()
            ]
        return build_plan_summary(tasks, mastery, reviews)
