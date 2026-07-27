from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TeacherRepository:
    """Small local assignment store sharing the session database.

    Assignments are archived instead of hard-deleted. Report snapshots contain
    immutable JSON so later session changes cannot silently rewrite history.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS teacher_assignments (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    due_at TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    session_ids_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_teacher_assignment_user
                    ON teacher_assignments(user_id, status, updated_at DESC);
                CREATE TABLE IF NOT EXISTS teacher_report_snapshots (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    assignment_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_teacher_snapshot_user
                    ON teacher_report_snapshots(user_id, created_at DESC);
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _assignment(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "title": str(row["title"]),
            "description": str(row["description"] or ""),
            "due_at": row["due_at"],
            "status": str(row["status"]),
            "session_ids": json.loads(row["session_ids_json"] or "[]"),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def list_assignments(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM teacher_assignments WHERE user_id = ? "
                "ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'completed' THEN 1 ELSE 2 END, updated_at DESC",
                (user_id,),
            ).fetchall()
        return [self._assignment(row) for row in rows]

    def get_assignment(self, user_id: str, assignment_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM teacher_assignments WHERE user_id = ? AND id = ?",
                (user_id, assignment_id),
            ).fetchone()
        return self._assignment(row) if row else None

    def create_assignment(
        self, user_id: str, title: str, description: str, due_at: str | None
    ) -> dict[str, Any]:
        assignment_id = f"assignment-{uuid.uuid4().hex}"
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO teacher_assignments "
                "(id,user_id,title,description,due_at,status,session_ids_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?,'active','[]',?,?)",
                (assignment_id, user_id, title, description, due_at, now, now),
            )
            connection.commit()
        return self.get_assignment(user_id, assignment_id) or {}

    def update_assignment(
        self,
        user_id: str,
        assignment_id: str,
        *,
        title: str,
        description: str,
        due_at: str | None,
        status: str,
        session_ids: list[str],
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE teacher_assignments SET title=?,description=?,due_at=?,status=?,"
                "session_ids_json=?,updated_at=? WHERE user_id=? AND id=?",
                (
                    title,
                    description,
                    due_at,
                    status,
                    json.dumps(list(dict.fromkeys(session_ids)), ensure_ascii=False),
                    utc_now(),
                    user_id,
                    assignment_id,
                ),
            )
            connection.commit()
        return self.get_assignment(user_id, assignment_id)

    def create_snapshot(
        self, user_id: str, assignment_id: str, title: str, report: dict[str, Any]
    ) -> dict[str, Any]:
        snapshot_id = f"teacher-report-{uuid.uuid4().hex}"
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO teacher_report_snapshots "
                "(id,user_id,assignment_id,title,report_json,created_at) VALUES (?,?,?,?,?,?)",
                (
                    snapshot_id,
                    user_id,
                    assignment_id,
                    title,
                    json.dumps(report, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            connection.commit()
        return {
            "id": snapshot_id,
            "assignment_id": assignment_id,
            "title": title,
            "created_at": now,
            "report": report,
        }

    def list_snapshots(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM teacher_report_snapshots WHERE user_id=? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "assignment_id": str(row["assignment_id"]),
                "title": str(row["title"]),
                "created_at": str(row["created_at"]),
                "report": json.loads(row["report_json"]),
            }
            for row in rows
        ]
