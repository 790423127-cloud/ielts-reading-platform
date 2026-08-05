from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid
from typing import Any

from app.repositories.schema_migrations import component_schema_migration


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TeacherRepository:
    """Small local assignment store sharing the session database.

    Assignments are archived instead of hard-deleted. Report snapshots contain
    immutable JSON so later session changes cannot silently rewrite history.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        with component_schema_migration(
            self.database_path,
            component="teacher",
            version=1,
        ) as connection:
            if connection is None:
                return
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
                CREATE TABLE IF NOT EXISTS teacher_assignment_modules (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    assignment_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    module_type TEXT NOT NULL DEFAULT 'mixed',
                    target_count INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_teacher_module_assignment
                    ON teacher_assignment_modules(user_id, assignment_id, sort_order);
                CREATE TABLE IF NOT EXISTS teacher_assignment_sessions (
                    user_id TEXT NOT NULL,
                    assignment_id TEXT NOT NULL,
                    module_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    attempt_kind TEXT NOT NULL DEFAULT 'practice',
                    linked_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, assignment_id, module_id, session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_teacher_assignment_session
                    ON teacher_assignment_sessions(user_id, assignment_id, session_id);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _modules(
        connection: sqlite3.Connection,
        *,
        user_id: str,
        assignment_id: str,
        legacy_session_ids: list[str],
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT * FROM teacher_assignment_modules
            WHERE user_id = ? AND assignment_id = ?
            ORDER BY sort_order, created_at, id
            """,
            (user_id, assignment_id),
        ).fetchall()
        if not rows:
            return [{
                "id": f"legacy-{assignment_id}",
                "title": "练习模块 1",
                "module_type": "mixed",
                "target_count": len(legacy_session_ids),
                "sort_order": 0,
                "session_ids": legacy_session_ids,
            }]
        links = connection.execute(
            """
            SELECT module_id, session_id FROM teacher_assignment_sessions
            WHERE user_id = ? AND assignment_id = ?
            ORDER BY linked_at, session_id
            """,
            (user_id, assignment_id),
        ).fetchall()
        session_ids_by_module: dict[str, list[str]] = {}
        for link in links:
            session_ids_by_module.setdefault(str(link["module_id"]), []).append(
                str(link["session_id"])
            )
        return [
            {
                "id": str(row["id"]),
                "title": str(row["title"]),
                "module_type": str(row["module_type"]),
                "target_count": int(row["target_count"] or 0),
                "sort_order": int(row["sort_order"] or 0),
                "session_ids": session_ids_by_module.get(str(row["id"]), []),
            }
            for row in rows
        ]

    @classmethod
    def _assignment(
        cls,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> dict[str, Any]:
        legacy_session_ids = json.loads(row["session_ids_json"] or "[]")
        modules = cls._modules(
            connection,
            user_id=str(row["user_id"]),
            assignment_id=str(row["id"]),
            legacy_session_ids=legacy_session_ids,
        )
        session_ids = list(dict.fromkeys(
            session_id
            for module in modules
            for session_id in module["session_ids"]
        ))
        return {
            "id": str(row["id"]),
            "title": str(row["title"]),
            "description": str(row["description"] or ""),
            "due_at": row["due_at"],
            "status": str(row["status"]),
            "session_ids": session_ids,
            "modules": modules,
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
            return [self._assignment(connection, row) for row in rows]

    def get_assignment(self, user_id: str, assignment_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM teacher_assignments WHERE user_id = ? AND id = ?",
                (user_id, assignment_id),
            ).fetchone()
            return self._assignment(connection, row) if row else None

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
            connection.execute(
                """
                INSERT INTO teacher_assignment_modules (
                    id,user_id,assignment_id,title,module_type,target_count,
                    sort_order,created_at,updated_at
                ) VALUES (?,?,?,?,?,0,0,?,?)
                """,
                (
                    f"module-{uuid.uuid4().hex}",
                    user_id,
                    assignment_id,
                    "练习模块 1",
                    "mixed",
                    now,
                    now,
                ),
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
        modules: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        normalized_modules = modules
        if normalized_modules is None:
            normalized_modules = [{
                "id": f"module-{uuid.uuid4().hex}",
                "title": "练习模块 1",
                "module_type": "mixed",
                "target_count": len(session_ids),
                "session_ids": session_ids,
            }]
        normalized_modules = normalized_modules or [{
            "id": f"module-{uuid.uuid4().hex}",
            "title": "练习模块 1",
            "module_type": "mixed",
            "target_count": 0,
            "session_ids": [],
        }]
        flattened_session_ids = list(dict.fromkeys(
            str(session_id)
            for module in normalized_modules
            for session_id in (module.get("session_ids") or [])
        ))
        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE teacher_assignments SET title=?,description=?,due_at=?,status=?,"
                "session_ids_json=?,updated_at=? WHERE user_id=? AND id=?",
                (
                    title,
                    description,
                    due_at,
                    status,
                    json.dumps(flattened_session_ids, ensure_ascii=False),
                    now,
                    user_id,
                    assignment_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            connection.execute(
                "DELETE FROM teacher_assignment_sessions WHERE user_id=? AND assignment_id=?",
                (user_id, assignment_id),
            )
            connection.execute(
                "DELETE FROM teacher_assignment_modules WHERE user_id=? AND assignment_id=?",
                (user_id, assignment_id),
            )
            for sort_order, module in enumerate(normalized_modules):
                module_id = str(module.get("id") or f"module-{uuid.uuid4().hex}")
                connection.execute(
                    """
                    INSERT INTO teacher_assignment_modules (
                        id,user_id,assignment_id,title,module_type,target_count,
                        sort_order,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        module_id,
                        user_id,
                        assignment_id,
                        str(module.get("title") or f"练习模块 {sort_order + 1}"),
                        str(module.get("module_type") or "mixed"),
                        max(0, int(module.get("target_count") or 0)),
                        sort_order,
                        now,
                        now,
                    ),
                )
                for session_id in dict.fromkeys(module.get("session_ids") or []):
                    connection.execute(
                        """
                        INSERT INTO teacher_assignment_sessions (
                            user_id,assignment_id,module_id,session_id,attempt_kind,linked_at
                        ) VALUES (?,?,?,?,?,?)
                        """,
                        (
                            user_id,
                            assignment_id,
                            module_id,
                            str(session_id),
                            "practice",
                            now,
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

    def get_snapshot(self, user_id: str, snapshot_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM teacher_report_snapshots
                WHERE user_id = ? AND id = ?
                """,
                (user_id, snapshot_id),
            ).fetchone()
        if not row:
            return None
        return {
            "id": str(row["id"]),
            "assignment_id": str(row["assignment_id"]),
            "title": str(row["title"]),
            "created_at": str(row["created_at"]),
            "report": json.loads(row["report_json"]),
        }
