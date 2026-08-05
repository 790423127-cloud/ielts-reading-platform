from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from app.repositories.schema_migrations import component_schema_migration


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AiJobRepository:
    """Persistent per-question AI queue with idempotency and lease recovery."""

    MAX_ATTEMPTS = 3

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        with component_schema_migration(
            self.database_path,
            component="ai_jobs",
            version=1,
        ) as connection:
            if connection is None:
                return
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS durable_ai_jobs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    total_items INTEGER NOT NULL,
                    completed_items INTEGER NOT NULL DEFAULT 0,
                    failed_items INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_durable_ai_jobs_user
                    ON durable_ai_jobs(user_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS durable_ai_job_items (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    question_number INTEGER,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    worker_token TEXT,
                    lease_expires_at TEXT,
                    result_json TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(job_id, question_id)
                );
                CREATE INDEX IF NOT EXISTS idx_durable_ai_items_claim
                    ON durable_ai_job_items(user_id, job_id, status, created_at);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _item(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "question_id": str(row["question_id"]),
            "question_number": row["question_number"],
            "status": str(row["status"]),
            "attempt_count": int(row["attempt_count"]),
            "lease_expires_at": row["lease_expires_at"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error_message": str(row["error_message"]) if row["error_message"] else None,
            "updated_at": str(row["updated_at"]),
        }

    @classmethod
    def _job(cls, connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        items = connection.execute(
            """
            SELECT * FROM durable_ai_job_items
            WHERE job_id = ? AND user_id = ?
            ORDER BY question_number, created_at, id
            """,
            (str(row["id"]), str(row["user_id"])),
        ).fetchall()
        return {
            "id": str(row["id"]),
            "session_id": str(row["session_id"]),
            "idempotency_key": str(row["idempotency_key"]),
            "status": str(row["status"]),
            "provider": str(row["provider"]),
            "model": str(row["model"]),
            "total_items": int(row["total_items"]),
            "completed_items": int(row["completed_items"]),
            "failed_items": int(row["failed_items"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "items": [cls._item(item) for item in items],
            "policy": {
                "creation_calls_ai": False,
                "resume_processes_at_most": 1,
                "max_attempts_per_item": cls.MAX_ATTEMPTS,
                "automatic_paid_provider_fallback": False,
            },
        }

    def create_or_get(
        self,
        *,
        user_id: str,
        session_id: str,
        idempotency_key: str,
        provider: str,
        model: str,
        questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        clean_key = idempotency_key.strip()
        now = utc_now().isoformat()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM durable_ai_jobs WHERE user_id=? AND idempotency_key=?",
                (user_id, clean_key),
            ).fetchone()
            if existing:
                existing_question_ids = {
                    str(row["question_id"])
                    for row in connection.execute(
                        "SELECT question_id FROM durable_ai_job_items WHERE job_id=?",
                        (str(existing["id"]),),
                    ).fetchall()
                }
                requested = {str(row["id"]) for row in questions}
                if (
                    str(existing["session_id"]) != session_id
                    or existing_question_ids != requested
                ):
                    raise ValueError("idempotency_key_conflict")
                return self._job(connection, existing)
            job_id = f"ai-job-{uuid.uuid4().hex}"
            connection.execute(
                """
                INSERT INTO durable_ai_jobs (
                    id,user_id,session_id,idempotency_key,status,provider,model,
                    total_items,completed_items,failed_items,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?, ?,0,0,?,?)
                """,
                (
                    job_id,
                    user_id,
                    session_id,
                    clean_key,
                    "pending",
                    provider,
                    model,
                    len(questions),
                    now,
                    now,
                ),
            )
            for question in questions:
                connection.execute(
                    """
                    INSERT INTO durable_ai_job_items (
                        id,job_id,user_id,session_id,question_id,question_number,
                        status,attempt_count,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?, 'pending',0,?,?)
                    """,
                    (
                        f"ai-item-{uuid.uuid4().hex}",
                        job_id,
                        user_id,
                        session_id,
                        str(question["id"]),
                        int(question.get("number") or 0) or None,
                        now,
                        now,
                    ),
                )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM durable_ai_jobs WHERE id=?", (job_id,)
            ).fetchone()
            return self._job(connection, row)

    def list_jobs(self, user_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM durable_ai_jobs
                WHERE user_id = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            return [self._job(connection, row) for row in rows]

    def get_job(self, user_id: str, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM durable_ai_jobs WHERE user_id=? AND id=?",
                (user_id, job_id),
            ).fetchone()
            return self._job(connection, row) if row else None

    def _refresh_job_status(self, connection: sqlite3.Connection, job_id: str) -> None:
        counts = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN status IN ('pending','in_progress') THEN 1 ELSE 0 END) AS remaining
            FROM durable_ai_job_items WHERE job_id=?
            """,
            (job_id,),
        ).fetchone()
        completed = int(counts["completed"] or 0)
        failed = int(counts["failed"] or 0)
        remaining = int(counts["remaining"] or 0)
        if remaining:
            status = "running" if connection.execute(
                "SELECT 1 FROM durable_ai_job_items WHERE job_id=? AND status='in_progress' LIMIT 1",
                (job_id,),
            ).fetchone() else "pending"
        elif failed:
            status = "partial" if completed else "failed"
        else:
            status = "completed"
        connection.execute(
            """
            UPDATE durable_ai_jobs SET status=?,completed_items=?,failed_items=?,updated_at=?
            WHERE id=?
            """,
            (status, completed, failed, utc_now().isoformat(), job_id),
        )

    def claim_next(
        self,
        *,
        user_id: str,
        job_id: str,
        lease_seconds: int = 120,
    ) -> dict[str, Any] | None:
        now = utc_now()
        now_text = now.isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            owner = connection.execute(
                "SELECT 1 FROM durable_ai_jobs WHERE user_id=? AND id=?",
                (user_id, job_id),
            ).fetchone()
            if not owner:
                connection.rollback()
                return None
            connection.execute(
                """
                UPDATE durable_ai_job_items
                SET status=CASE WHEN attempt_count >= ? THEN 'failed' ELSE 'pending' END,
                    worker_token=NULL, lease_expires_at=NULL,
                    error_message=CASE WHEN attempt_count >= ? THEN
                        COALESCE(error_message, '任务租约到期且已达到最大重试次数')
                        ELSE error_message END,
                    updated_at=?
                WHERE user_id=? AND job_id=? AND status='in_progress'
                    AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
                """,
                (
                    self.MAX_ATTEMPTS,
                    self.MAX_ATTEMPTS,
                    now_text,
                    user_id,
                    job_id,
                    now_text,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM durable_ai_job_items
                WHERE user_id=? AND job_id=? AND status='pending'
                    AND attempt_count < ?
                ORDER BY question_number, created_at, id
                LIMIT 1
                """,
                (user_id, job_id, self.MAX_ATTEMPTS),
            ).fetchone()
            if not row:
                self._refresh_job_status(connection, job_id)
                connection.commit()
                return None
            token = uuid.uuid4().hex
            lease = (now + timedelta(seconds=max(30, lease_seconds))).isoformat()
            connection.execute(
                """
                UPDATE durable_ai_job_items
                SET status='in_progress',attempt_count=attempt_count+1,
                    worker_token=?,lease_expires_at=?,error_message=NULL,updated_at=?
                WHERE id=? AND status='pending'
                """,
                (token, lease, now_text, str(row["id"])),
            )
            self._refresh_job_status(connection, job_id)
            connection.commit()
            claimed = connection.execute(
                "SELECT * FROM durable_ai_job_items WHERE id=?",
                (str(row["id"]),),
            ).fetchone()
            return {**self._item(claimed), "worker_token": token}

    def complete(
        self,
        *,
        user_id: str,
        job_id: str,
        item_id: str,
        worker_token: str,
        result: dict[str, Any],
    ) -> bool:
        now = utc_now().isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE durable_ai_job_items
                SET status='completed',result_json=?,error_message=NULL,
                    worker_token=NULL,lease_expires_at=NULL,updated_at=?
                WHERE id=? AND job_id=? AND user_id=? AND status='in_progress'
                    AND worker_token=?
                """,
                (
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    now,
                    item_id,
                    job_id,
                    user_id,
                    worker_token,
                ),
            )
            self._refresh_job_status(connection, job_id)
            connection.commit()
            return cursor.rowcount == 1

    def fail(
        self,
        *,
        user_id: str,
        job_id: str,
        item_id: str,
        worker_token: str,
        message: str,
        retryable: bool,
    ) -> bool:
        now = utc_now().isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT attempt_count FROM durable_ai_job_items
                WHERE id=? AND job_id=? AND user_id=? AND status='in_progress'
                    AND worker_token=?
                """,
                (item_id, job_id, user_id, worker_token),
            ).fetchone()
            if not row:
                return False
            status = (
                "pending"
                if retryable and int(row["attempt_count"]) < self.MAX_ATTEMPTS
                else "failed"
            )
            connection.execute(
                """
                UPDATE durable_ai_job_items
                SET status=?,error_message=?,worker_token=NULL,
                    lease_expires_at=NULL,updated_at=?
                WHERE id=? AND job_id=? AND user_id=? AND worker_token=?
                """,
                (status, message[:1000], now, item_id, job_id, user_id, worker_token),
            )
            self._refresh_job_status(connection, job_id)
            connection.commit()
            return True
