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
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user_created "
                "ON sessions(user_id, created_at DESC)"
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
        )

    def get(self, *, user_id: str, session_id: str) -> StoredSession | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE user_id = ? AND id = ?",
                (user_id, session_id),
            ).fetchone()
        return self._from_row(row, replay=False) if row else None
