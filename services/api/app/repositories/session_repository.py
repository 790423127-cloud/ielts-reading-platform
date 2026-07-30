from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid
from typing import Any


@dataclass(frozen=True, slots=True)
class StoredSession:
    id: str
    user_id: str
    client_submission_id: str
    test_id: str
    result: dict[str, Any]
    created_at: str
    idempotent_replay: bool
    archived_at: str | None = None


class SQLiteSessionRepository:
    """SQLite reference repository with per-user idempotent submissions."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    client_submission_id TEXT NOT NULL,
                    test_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    total INTEGER NOT NULL,
                    result_json TEXT NOT NULL,
                    UNIQUE(user_id, client_submission_id)
                )
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "archived_at" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN archived_at TEXT")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user_created "
                "ON sessions(user_id, created_at DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def get_setting(self, key: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key.strip(),),
            ).fetchone()
        return str(row["value"]) if row else None

    def set_setting(self, key: str, value: str) -> None:
        clean_key = key.strip()
        if not clean_key:
            raise ValueError("setting key is required")
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (clean_key, value, updated_at),
            )
            connection.commit()

    @staticmethod
    def _from_row(row: sqlite3.Row, *, replay: bool) -> StoredSession:
        return StoredSession(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            client_submission_id=str(row["client_submission_id"]),
            test_id=str(row["test_id"]),
            result=json.loads(row["result_json"]),
            created_at=str(row["created_at"]),
            idempotent_replay=replay,
            archived_at=str(row["archived_at"]) if row["archived_at"] else None,
        )

    def get_by_client_submission_id(
        self, user_id: str, client_submission_id: str
    ) -> StoredSession | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE user_id = ? AND client_submission_id = ?",
                (user_id, client_submission_id),
            ).fetchone()
        return self._from_row(row, replay=True) if row else None

    def save_or_get(
        self,
        *,
        user_id: str,
        client_submission_id: str,
        test_id: str,
        result: dict[str, Any],
    ) -> StoredSession:
        clean_user_id = user_id.strip()
        clean_client_id = client_submission_id.strip()
        if not clean_user_id:
            raise ValueError("user_id is required")
        if not clean_client_id:
            raise ValueError("client_submission_id is required")

        existing = self.get_by_client_submission_id(clean_user_id, clean_client_id)
        if existing:
            return existing

        session_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO sessions (
                        id, user_id, client_submission_id, test_id, created_at,
                        score, total, result_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        clean_user_id,
                        clean_client_id,
                        test_id,
                        created_at,
                        int(result.get("score") or 0),
                        int(result.get("total") or 0),
                        payload,
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError:
                row = connection.execute(
                    "SELECT * FROM sessions WHERE user_id = ? AND client_submission_id = ?",
                    (clean_user_id, clean_client_id),
                ).fetchone()
                if row:
                    return self._from_row(row, replay=True)
                raise
        return StoredSession(
            id=session_id,
            user_id=clean_user_id,
            client_submission_id=clean_client_id,
            test_id=test_id,
            result=result,
            created_at=created_at,
            idempotent_replay=False,
            archived_at=None,
        )

    def get(self, *, user_id: str, session_id: str) -> StoredSession | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE user_id = ? AND id = ?",
                (user_id, session_id),
            ).fetchone()
        return self._from_row(row, replay=False) if row else None

    def list_recent(
        self, *, user_id: str, limit: int = 20, include_archived: bool = False
    ) -> list[StoredSession]:
        clean_user_id = user_id.strip()
        bounded_limit = max(1, min(int(limit), 1000))
        with self._connect() as connection:
            archived_clause = "" if include_archived else " AND archived_at IS NULL"
            rows = connection.execute(
                f"SELECT * FROM sessions WHERE user_id = ?{archived_clause} "
                "ORDER BY created_at DESC LIMIT ?",
                (clean_user_id, bounded_limit),
            ).fetchall()
        return [self._from_row(row, replay=False) for row in rows]

    def archive(self, *, user_id: str, session_id: str) -> bool:
        archived_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE sessions SET archived_at = ? WHERE user_id = ? AND id = ?",
                (archived_at, user_id.strip(), session_id),
            )
            connection.commit()
        return cursor.rowcount > 0

    def delete(
        self,
        *,
        user_id: str,
        session_id: str,
    ) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM sessions WHERE user_id = ? AND id = ?",
                (user_id.strip(), session_id.strip()),
            )
            connection.commit()
        return cursor.rowcount > 0

    def delete_many(
        self,
        *,
        user_id: str,
        session_ids: list[str],
    ) -> tuple[list[str], list[str]]:
        clean_user_id = user_id.strip()
        unique_ids = list(dict.fromkeys(
            session_id.strip()
            for session_id in session_ids
            if session_id.strip()
        ))
        if not unique_ids:
            return [], []
        placeholders = ",".join("?" for _ in unique_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT id FROM sessions WHERE user_id = ? AND id IN ({placeholders})",
                [clean_user_id, *unique_ids],
            ).fetchall()
            found_ids = {str(row["id"]) for row in rows}
            deleted_ids = [
                session_id for session_id in unique_ids if session_id in found_ids
            ]
            if deleted_ids:
                delete_placeholders = ",".join("?" for _ in deleted_ids)
                connection.execute(
                    f"DELETE FROM sessions "
                    f"WHERE user_id = ? AND id IN ({delete_placeholders})",
                    [clean_user_id, *deleted_ids],
                )
            connection.commit()
        missing_ids = [
            session_id for session_id in unique_ids if session_id not in found_ids
        ]
        return deleted_ids, missing_ids

    def restore(self, *, user_id: str, session_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE sessions SET archived_at = NULL WHERE user_id = ? AND id = ?",
                (user_id.strip(), session_id),
            )
            connection.commit()
        return cursor.rowcount > 0
