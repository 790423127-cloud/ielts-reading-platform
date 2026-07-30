from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
from typing import Any
import uuid


VOCABULARY_STATUSES = {"learning", "mastered"}


def normalize_term(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


class VocabularyRepository:
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
                CREATE TABLE IF NOT EXISTS vocabulary_items (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    term TEXT NOT NULL,
                    term_norm TEXT NOT NULL,
                    meaning TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'learning',
                    occurrence_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, term_norm)
                );
                CREATE INDEX IF NOT EXISTS idx_vocabulary_items_user_updated
                    ON vocabulary_items(user_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS vocabulary_sources (
                    id TEXT PRIMARY KEY,
                    vocabulary_id TEXT NOT NULL,
                    source_key TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_sentence TEXT,
                    source_context TEXT,
                    source_session_id TEXT,
                    source_question_id TEXT,
                    test_id TEXT,
                    test_title TEXT,
                    part_number INTEGER,
                    created_at TEXT NOT NULL,
                    UNIQUE(vocabulary_id, source_key),
                    FOREIGN KEY(vocabulary_id) REFERENCES vocabulary_items(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_vocabulary_sources_item_created
                    ON vocabulary_sources(vocabulary_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS vocabulary_exports (
                    user_id TEXT NOT NULL,
                    vocabulary_id TEXT NOT NULL,
                    exported_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, vocabulary_id),
                    FOREIGN KEY(vocabulary_id) REFERENCES vocabulary_items(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_vocabulary_exports_user
                    ON vocabulary_exports(user_id, exported_at DESC);
                """
            )
            connection.commit()

    @staticmethod
    def _source_key(payload: dict[str, Any]) -> str:
        parts = [
            str(payload.get("source_type") or "manual").strip(),
            str(payload.get("source_sentence") or "").strip(),
            str(payload.get("source_context") or "").strip(),
            str(payload.get("source_session_id") or "").strip(),
            str(payload.get("source_question_id") or "").strip(),
            str(payload.get("test_id") or "").strip(),
            str(payload.get("part_number") or "").strip(),
        ]
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    @staticmethod
    def _source_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "source_type": str(row["source_type"]),
            "source_sentence": row["source_sentence"],
            "source_context": row["source_context"],
            "source_session_id": row["source_session_id"],
            "source_question_id": row["source_question_id"],
            "test_id": row["test_id"],
            "test_title": row["test_title"],
            "part_number": row["part_number"],
            "created_at": str(row["created_at"]),
        }

    def _item_from_row(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        deduplicated: bool = False,
        source_added: bool = False,
    ) -> dict[str, Any]:
        sources = connection.execute(
            "SELECT * FROM vocabulary_sources WHERE vocabulary_id = ? "
            "ORDER BY created_at DESC, id",
            (row["id"],),
        ).fetchall()
        export_row = connection.execute(
            "SELECT exported_at FROM vocabulary_exports WHERE user_id = ? AND vocabulary_id = ?",
            (row["user_id"], row["id"]),
        ).fetchone()
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "term": str(row["term"]),
            "meaning": str(row["meaning"] or ""),
            "note": str(row["note"] or ""),
            "status": str(row["status"]),
            "occurrence_count": int(row["occurrence_count"] or 0),
            "sources": [self._source_from_row(source) for source in sources],
            "exported_before": export_row is not None,
            "last_exported_at": str(export_row["exported_at"]) if export_row else None,
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "deduplicated": deduplicated,
            "source_added": source_added,
        }

    def capture(
        self,
        *,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        term = " ".join(str(payload.get("term") or "").strip().split())
        term_norm = normalize_term(term)
        if not term_norm:
            raise ValueError("Vocabulary term is required")
        meaning = str(payload.get("meaning") or "").strip()
        note = str(payload.get("note") or "").strip()
        now = self._now()
        source_key = self._source_key(payload)

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM vocabulary_items WHERE user_id = ? AND term_norm = ?",
                (user_id, term_norm),
            ).fetchone()
            deduplicated = existing is not None
            if existing:
                item_id = str(existing["id"])
                next_meaning = str(existing["meaning"] or "") or meaning
                next_note = str(existing["note"] or "") or note
                connection.execute(
                    "UPDATE vocabulary_items SET meaning = ?, note = ?, updated_at = ? WHERE id = ?",
                    (next_meaning, next_note, now, item_id),
                )
            else:
                item_id = uuid.uuid4().hex
                connection.execute(
                    """
                    INSERT INTO vocabulary_items (
                        id, user_id, term, term_norm, meaning, note,
                        status, occurrence_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'learning', 0, ?, ?)
                    """,
                    (item_id, user_id, term, term_norm, meaning, note, now, now),
                )

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO vocabulary_sources (
                    id, vocabulary_id, source_key, source_type, source_sentence,
                    source_context, source_session_id, source_question_id,
                    test_id, test_title, part_number, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    item_id,
                    source_key,
                    str(payload.get("source_type") or "manual"),
                    str(payload.get("source_sentence") or "").strip() or None,
                    str(payload.get("source_context") or "").strip() or None,
                    str(payload.get("source_session_id") or "").strip() or None,
                    str(payload.get("source_question_id") or "").strip() or None,
                    str(payload.get("test_id") or "").strip() or None,
                    str(payload.get("test_title") or "").strip() or None,
                    int(payload["part_number"]) if payload.get("part_number") is not None else None,
                    now,
                ),
            )
            source_added = bool(cursor.rowcount)
            source_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM vocabulary_sources WHERE vocabulary_id = ?",
                    (item_id,),
                ).fetchone()[0]
            )
            connection.execute(
                "UPDATE vocabulary_items SET occurrence_count = ?, updated_at = ? WHERE id = ?",
                (source_count, now, item_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM vocabulary_items WHERE id = ?",
                (item_id,),
            ).fetchone()
            return self._item_from_row(
                connection,
                row,
                deduplicated=deduplicated,
                source_added=source_added,
            )

    def list_items(
        self,
        *,
        user_id: str,
        query: str = "",
        status: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 5000))
        clauses = ["user_id = ?"]
        params: list[Any] = [user_id]
        normalized_query = normalize_term(query)
        if normalized_query:
            clauses.append("(term_norm LIKE ? OR lower(meaning) LIKE ? OR lower(note) LIKE ?)")
            pattern = f"%{normalized_query}%"
            params.extend([pattern, pattern, pattern])
        if status in VOCABULARY_STATUSES:
            clauses.append("status = ?")
            params.append(status)
        params.append(bounded)
        sql = (
            "SELECT * FROM vocabulary_items WHERE "
            + " AND ".join(clauses)
            + " ORDER BY updated_at DESC, term_norm LIMIT ?"
        )
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
            return [self._item_from_row(connection, row) for row in rows]

    def items_by_ids(self, *, user_id: str, item_ids: list[str]) -> list[dict[str, Any]]:
        ordered_ids = list(dict.fromkeys(str(item_id) for item_id in item_ids if item_id))
        if not ordered_ids:
            return []
        placeholders = ",".join("?" for _ in ordered_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM vocabulary_items WHERE user_id = ? AND id IN ({placeholders})",
                [user_id, *ordered_ids],
            ).fetchall()
            by_id = {
                str(row["id"]): self._item_from_row(connection, row)
                for row in rows
            }
        return [by_id[item_id] for item_id in ordered_ids if item_id in by_id]

    def mark_exported(self, *, user_id: str, item_ids: list[str]) -> int:
        ids = list(dict.fromkeys(str(item_id) for item_id in item_ids if item_id))
        if not ids:
            return 0
        now = self._now()
        with self._connect() as connection:
            for item_id in ids:
                connection.execute(
                    """
                    INSERT INTO vocabulary_exports (user_id, vocabulary_id, exported_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, vocabulary_id)
                    DO UPDATE SET exported_at = excluded.exported_at
                    """,
                    (user_id, item_id, now),
                )
            connection.commit()
        return len(ids)

    def get_item(self, *, user_id: str, item_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM vocabulary_items WHERE user_id = ? AND id = ?",
                (user_id, item_id),
            ).fetchone()
            return self._item_from_row(connection, row) if row else None

    def update_item(
        self,
        *,
        user_id: str,
        item_id: str,
        meaning: str,
        note: str,
        status: str,
    ) -> dict[str, Any] | None:
        if status not in VOCABULARY_STATUSES:
            raise ValueError("Unsupported vocabulary status")
        now = self._now()
        with self._connect() as connection:
            current = connection.execute(
                "SELECT * FROM vocabulary_items WHERE user_id = ? AND id = ?",
                (user_id, item_id),
            ).fetchone()
            if not current:
                return None
            connection.execute(
                "UPDATE vocabulary_items SET meaning = ?, note = ?, status = ?, updated_at = ? "
                "WHERE user_id = ? AND id = ?",
                (meaning.strip(), note.strip(), status, now, user_id, item_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM vocabulary_items WHERE user_id = ? AND id = ?",
                (user_id, item_id),
            ).fetchone()
            return self._item_from_row(connection, row)

    def delete_item(self, *, user_id: str, item_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                "DELETE FROM vocabulary_items WHERE user_id = ? AND id = ?",
                (user_id, item_id),
            )
            connection.commit()
            return bool(result.rowcount)
