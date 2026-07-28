from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any


class ReviewFeedbackRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS wrong_question_feedback (
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    match_status TEXT NOT NULL,
                    understanding_status TEXT NOT NULL,
                    cause_id TEXT,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, session_id, question_id)
                );
                CREATE INDEX IF NOT EXISTS idx_wrong_feedback_user_updated
                    ON wrong_question_feedback(user_id, updated_at DESC);
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "session_id": str(row["session_id"]),
            "question_id": str(row["question_id"]),
            "match_status": str(row["match_status"]),
            "understanding_status": str(row["understanding_status"]),
            "cause_id": str(row["cause_id"]) if row["cause_id"] else None,
            "note": str(row["note"] or ""),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def list_for_user(self, user_id: str) -> dict[tuple[str, str], dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM wrong_question_feedback WHERE user_id = ?",
                (user_id.strip(),),
            ).fetchall()
        return {
            (str(row["session_id"]), str(row["question_id"])): self._row(row)
            for row in rows
        }

    def save(
        self,
        *,
        user_id: str,
        session_id: str,
        question_id: str,
        match_status: str,
        understanding_status: str,
        cause_id: str | None,
        note: str,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO wrong_question_feedback (
                    user_id, session_id, question_id, match_status,
                    understanding_status, cause_id, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, session_id, question_id) DO UPDATE SET
                    match_status = excluded.match_status,
                    understanding_status = excluded.understanding_status,
                    cause_id = excluded.cause_id,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id.strip(),
                    session_id,
                    question_id,
                    match_status,
                    understanding_status,
                    cause_id,
                    note,
                    now,
                    now,
                ),
            )
            connection.commit()
            row = connection.execute(
                """
                SELECT * FROM wrong_question_feedback
                WHERE user_id = ? AND session_id = ? AND question_id = ?
                """,
                (user_id.strip(), session_id, question_id),
            ).fetchone()
        return self._row(row)
