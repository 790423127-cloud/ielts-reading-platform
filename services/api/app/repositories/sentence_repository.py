from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid
from typing import Any

from app.services.sentence_training import normalize_span


class SentenceRepository:
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
                CREATE TABLE IF NOT EXISTS sentence_training_attempts (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    client_submission_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    answers_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, client_submission_id)
                );
                CREATE INDEX IF NOT EXISTS idx_sentence_attempts_user_created
                    ON sentence_training_attempts(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS personal_sentences (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL,
                    sentence TEXT NOT NULL,
                    sentence_norm TEXT NOT NULL,
                    previous_sentence TEXT,
                    next_sentence TEXT,
                    paragraph TEXT,
                    source_type TEXT NOT NULL,
                    source_session_id TEXT,
                    source_question_id TEXT,
                    test_id TEXT,
                    test_title TEXT,
                    part_number INTEGER,
                    paragraph_index INTEGER,
                    exam_mode TEXT,
                    permission TEXT NOT NULL,
                    verified_item_id TEXT,
                    analysis_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, dedupe_key)
                );
                CREATE INDEX IF NOT EXISTS idx_personal_sentences_user_updated
                    ON personal_sentences(user_id, updated_at DESC);
                """
            )
            connection.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _attempt_from_row(row: sqlite3.Row, *, replay: bool) -> dict[str, Any]:
        return {
            "attempt_id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "client_submission_id": str(row["client_submission_id"]),
            "item_id": str(row["item_id"]),
            "answers": json.loads(row["answers_json"]),
            "result": json.loads(row["result_json"]),
            "created_at": str(row["created_at"]),
            "idempotent_replay": replay,
        }

    def save_training_attempt(
        self,
        *,
        user_id: str,
        client_submission_id: str,
        item_id: str,
        answers: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM sentence_training_attempts "
                "WHERE user_id = ? AND client_submission_id = ?",
                (user_id, client_submission_id),
            ).fetchone()
            if existing:
                return self._attempt_from_row(existing, replay=True)
            attempt_id = uuid.uuid4().hex
            created_at = self._now()
            connection.execute(
                """
                INSERT INTO sentence_training_attempts (
                    id, user_id, client_submission_id, item_id,
                    answers_json, result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    user_id,
                    client_submission_id,
                    item_id,
                    json.dumps(answers, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    created_at,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM sentence_training_attempts WHERE id = ?",
                (attempt_id,),
            ).fetchone()
        return self._attempt_from_row(row, replay=False)

    @staticmethod
    def _dedupe_key(payload: dict[str, Any]) -> str:
        normalized = normalize_span(payload.get("sentence"))
        parts = [
            normalized,
            str(payload.get("source_type") or "manual"),
            str(payload.get("source_session_id") or ""),
            str(payload.get("source_question_id") or ""),
            str(payload.get("test_id") or ""),
            str(payload.get("part_number") or ""),
        ]
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    @staticmethod
    def _sentence_from_row(row: sqlite3.Row, *, deduplicated: bool = False) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "sentence": str(row["sentence"]),
            "previous_sentence": row["previous_sentence"],
            "next_sentence": row["next_sentence"],
            "paragraph": row["paragraph"],
            "source_type": str(row["source_type"]),
            "source_session_id": row["source_session_id"],
            "source_question_id": row["source_question_id"],
            "test_id": row["test_id"],
            "test_title": row["test_title"],
            "part_number": row["part_number"],
            "paragraph_index": row["paragraph_index"],
            "exam_mode": row["exam_mode"],
            "permission": str(row["permission"]),
            "verified_item_id": row["verified_item_id"],
            "analysis": json.loads(row["analysis_json"] or "{}"),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "deduplicated": deduplicated,
            "standard_parse_available": str(row["permission"]) == "verified",
        }

    def capture_sentence(
        self,
        *,
        user_id: str,
        payload: dict[str, Any],
        permission: str,
        verified_item_id: str | None,
    ) -> dict[str, Any]:
        sentence = str(payload.get("sentence") or "").strip()
        if not sentence:
            raise ValueError("Sentence is required")
        dedupe_key = self._dedupe_key(payload)
        now = self._now()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM personal_sentences WHERE user_id = ? AND dedupe_key = ?",
                (user_id, dedupe_key),
            ).fetchone()
            if existing:
                connection.execute(
                    "UPDATE personal_sentences SET updated_at = ? WHERE id = ?",
                    (now, existing["id"]),
                )
                connection.commit()
                refreshed = connection.execute(
                    "SELECT * FROM personal_sentences WHERE id = ?",
                    (existing["id"],),
                ).fetchone()
                return self._sentence_from_row(refreshed, deduplicated=True)

            sentence_id = uuid.uuid4().hex
            connection.execute(
                """
                INSERT INTO personal_sentences (
                    id, user_id, dedupe_key, sentence, sentence_norm,
                    previous_sentence, next_sentence, paragraph, source_type,
                    source_session_id, source_question_id, test_id, test_title,
                    part_number, paragraph_index, exam_mode, permission,
                    verified_item_id, analysis_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                """,
                (
                    sentence_id,
                    user_id,
                    dedupe_key,
                    sentence,
                    normalize_span(sentence),
                    str(payload.get("previous_sentence") or "") or None,
                    str(payload.get("next_sentence") or "") or None,
                    str(payload.get("paragraph") or "") or None,
                    str(payload.get("source_type") or "manual"),
                    str(payload.get("source_session_id") or "") or None,
                    str(payload.get("source_question_id") or "") or None,
                    str(payload.get("test_id") or "") or None,
                    str(payload.get("test_title") or "") or None,
                    int(payload["part_number"]) if payload.get("part_number") is not None else None,
                    int(payload["paragraph_index"]) if payload.get("paragraph_index") is not None else None,
                    str(payload.get("exam_mode") or "") or None,
                    permission,
                    verified_item_id,
                    now,
                    now,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM personal_sentences WHERE id = ?",
                (sentence_id,),
            ).fetchone()
        return self._sentence_from_row(row)

    def list_sentences(self, *, user_id: str, limit: int = 200) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 500))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM personal_sentences WHERE user_id = ? "
                "ORDER BY updated_at DESC, id LIMIT ?",
                (user_id, bounded),
            ).fetchall()
        return [self._sentence_from_row(row) for row in rows]

    def get_sentence(self, *, user_id: str, sentence_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM personal_sentences WHERE user_id = ? AND id = ?",
                (user_id, sentence_id),
            ).fetchone()
        return self._sentence_from_row(row) if row else None

    def update_analysis(
        self,
        *,
        user_id: str,
        sentence_id: str,
        analysis: dict[str, Any],
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM personal_sentences WHERE user_id = ? AND id = ?",
                (user_id, sentence_id),
            ).fetchone()
            if not row:
                return None
            connection.execute(
                "UPDATE personal_sentences SET analysis_json = ?, updated_at = ? WHERE id = ?",
                (
                    json.dumps(analysis, ensure_ascii=False, separators=(",", ":")),
                    now,
                    sentence_id,
                ),
            )
            connection.commit()
            updated = connection.execute(
                "SELECT * FROM personal_sentences WHERE id = ?",
                (sentence_id,),
            ).fetchone()
        return self._sentence_from_row(updated)

    def delete_sentence(self, *, user_id: str, sentence_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                "DELETE FROM personal_sentences WHERE user_id = ? AND id = ?",
                (user_id, sentence_id),
            )
            connection.commit()
        return bool(result.rowcount)
