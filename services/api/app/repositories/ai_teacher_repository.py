from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
from typing import Any
import uuid


class AiTeacherRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ai_teacher_conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    context_type TEXT NOT NULL,
                    context_ref TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, context_type, context_ref)
                );
                CREATE INDEX IF NOT EXISTS idx_ai_conversations_user_updated
                    ON ai_teacher_conversations(user_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS ai_teacher_messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    model TEXT,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    cached INTEGER NOT NULL DEFAULT 0,
                    provider_request_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES ai_teacher_conversations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation_created
                    ON ai_teacher_messages(conversation_id, created_at, id);

                CREATE TABLE IF NOT EXISTS ai_teacher_cache (
                    cache_key TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    context_type TEXT NOT NULL,
                    context_ref TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    model TEXT,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    provider_request_id TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ai_cache_user_created
                    ON ai_teacher_cache(user_id, created_at DESC);
                """
            )
            connection.commit()

    @staticmethod
    def cache_key(*, user_id: str, context_type: str, context_ref: str, question: str) -> str:
        normalized_question = " ".join(question.strip().split()).casefold()
        raw = "\x1f".join([user_id, context_type, context_ref, normalized_question])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _message(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "role": str(row["role"]),
            "content": str(row["content"]),
            "model": row["model"],
            "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0),
            "cached": bool(row["cached"]),
            "provider_request_id": row["provider_request_id"],
            "created_at": str(row["created_at"]),
        }

    def _conversation(self, connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        messages = connection.execute(
            "SELECT * FROM ai_teacher_messages WHERE conversation_id = ? ORDER BY created_at, id",
            (row["id"],),
        ).fetchall()
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "context_type": str(row["context_type"]),
            "context_ref": str(row["context_ref"]),
            "title": str(row["title"]),
            "summary": str(row["summary"] or ""),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "messages": [self._message(message) for message in messages],
            "usage": {
                "input_tokens": sum(int(message["input_tokens"] or 0) for message in messages),
                "output_tokens": sum(int(message["output_tokens"] or 0) for message in messages),
                "provider_calls": sum(1 for message in messages if message["role"] == "assistant" and not message["cached"]),
                "cache_hits": sum(1 for message in messages if message["role"] == "assistant" and message["cached"]),
            },
        }

    def get_or_create_conversation(
        self,
        *,
        user_id: str,
        context_type: str,
        context_ref: str,
        title: str,
    ) -> dict[str, Any]:
        now = self._now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ai_teacher_conversations WHERE user_id = ? AND context_type = ? AND context_ref = ?",
                (user_id, context_type, context_ref),
            ).fetchone()
            if not row:
                conversation_id = uuid.uuid4().hex
                connection.execute(
                    """
                    INSERT INTO ai_teacher_conversations (
                        id, user_id, context_type, context_ref, title, summary, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, '', ?, ?)
                    """,
                    (conversation_id, user_id, context_type, context_ref, title[:300], now, now),
                )
                connection.commit()
                row = connection.execute(
                    "SELECT * FROM ai_teacher_conversations WHERE id = ?",
                    (conversation_id,),
                ).fetchone()
            return self._conversation(connection, row)

    def append_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        model: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached: bool = False,
        provider_request_id: str | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        with self._connect() as connection:
            conversation = connection.execute(
                "SELECT * FROM ai_teacher_conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not conversation:
                raise KeyError(conversation_id)
            connection.execute(
                """
                INSERT INTO ai_teacher_messages (
                    id, conversation_id, role, content, model, input_tokens,
                    output_tokens, cached, provider_request_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    conversation_id,
                    role,
                    content,
                    model,
                    max(0, int(input_tokens)),
                    max(0, int(output_tokens)),
                    int(cached),
                    provider_request_id,
                    now,
                ),
            )
            connection.execute(
                "UPDATE ai_teacher_conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
            self._refresh_summary(connection, conversation_id)
            connection.commit()
            row = connection.execute(
                "SELECT * FROM ai_teacher_conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            return self._conversation(connection, row)

    def _refresh_summary(self, connection: sqlite3.Connection, conversation_id: str) -> None:
        rows = connection.execute(
            "SELECT role, content FROM ai_teacher_messages WHERE conversation_id = ? ORDER BY created_at, id LIMIT 8",
            (conversation_id,),
        ).fetchall()
        fragments = []
        for row in rows:
            label = "问" if row["role"] == "user" else "答"
            text = " ".join(str(row["content"] or "").split())
            fragments.append(f"{label}：{text[:120]}")
        connection.execute(
            "UPDATE ai_teacher_conversations SET summary = ? WHERE id = ?",
            ("｜".join(fragments)[:1000], conversation_id),
        )

    def list_conversations(self, *, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 200))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM ai_teacher_conversations WHERE user_id = ? ORDER BY updated_at DESC, id LIMIT ?",
                (user_id, bounded),
            ).fetchall()
            return [self._conversation(connection, row) for row in rows]

    def get_conversation(self, *, user_id: str, conversation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ai_teacher_conversations WHERE user_id = ? AND id = ?",
                (user_id, conversation_id),
            ).fetchone()
            return self._conversation(connection, row) if row else None

    def delete_conversation(self, *, user_id: str, conversation_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                "DELETE FROM ai_teacher_conversations WHERE user_id = ? AND id = ?",
                (user_id, conversation_id),
            )
            connection.commit()
            return bool(result.rowcount)

    def get_cached(self, *, cache_key: str, user_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ai_teacher_cache WHERE cache_key = ? AND user_id = ?",
                (cache_key, user_id),
            ).fetchone()
            if not row:
                return None
            return {
                "answer": str(row["answer"]),
                "model": row["model"],
                "input_tokens": int(row["input_tokens"] or 0),
                "output_tokens": int(row["output_tokens"] or 0),
                "provider_request_id": row["provider_request_id"],
                "created_at": str(row["created_at"]),
            }

    def save_cache(
        self,
        *,
        cache_key: str,
        user_id: str,
        context_type: str,
        context_ref: str,
        question: str,
        answer: str,
        model: str | None,
        input_tokens: int,
        output_tokens: int,
        provider_request_id: str | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO ai_teacher_cache (
                    cache_key, user_id, context_type, context_ref, question, answer,
                    model, input_tokens, output_tokens, provider_request_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    user_id,
                    context_type,
                    context_ref,
                    question,
                    answer,
                    model,
                    max(0, int(input_tokens)),
                    max(0, int(output_tokens)),
                    provider_request_id,
                    self._now(),
                ),
            )
            connection.commit()

    def provider_calls_since(self, *, user_id: str, since: datetime) -> int:
        since_iso = since.astimezone(timezone.utc).isoformat()
        with self._connect() as connection:
            return int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM ai_teacher_messages messages
                    JOIN ai_teacher_conversations conversations
                      ON conversations.id = messages.conversation_id
                    WHERE conversations.user_id = ?
                      AND messages.role = 'assistant'
                      AND messages.cached = 0
                      AND messages.created_at >= ?
                    """,
                    (user_id, since_iso),
                ).fetchone()[0]
            )

    def provider_calls_today(self, *, user_id: str) -> int:
        now = datetime.now(timezone.utc)
        start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        return self.provider_calls_since(user_id=user_id, since=start)

    def delete_expired_cache(self, *, days: int = 30) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        with self._connect() as connection:
            result = connection.execute(
                "DELETE FROM ai_teacher_cache WHERE created_at < ?",
                (cutoff.isoformat(),),
            )
            connection.commit()
            return int(result.rowcount or 0)
