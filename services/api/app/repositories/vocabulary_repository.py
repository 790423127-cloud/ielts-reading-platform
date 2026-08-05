from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from app.repositories.schema_migrations import component_schema_migration


VOCABULARY_STATUSES = {"learning", "mastered"}
PARAPHRASE_STATUSES = {"learning", "mastered"}
PARAPHRASE_RELATION_TYPES = {
    "direct-paraphrase",
    "near-paraphrase",
    "contextual-paraphrase",
    "curated-paraphrase",
}


def normalize_term(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


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
        with component_schema_migration(
            self.database_path,
            component="vocabulary",
            version=2,
        ) as connection:
            if connection is None:
                return
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
                    manual_capture_count INTEGER NOT NULL DEFAULT 0,
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
                    content_fingerprint TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(user_id, vocabulary_id),
                    FOREIGN KEY(vocabulary_id) REFERENCES vocabulary_items(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_vocabulary_exports_user
                    ON vocabulary_exports(user_id, exported_at DESC);

                CREATE TABLE IF NOT EXISTS paraphrase_items (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    question_phrase TEXT NOT NULL,
                    question_phrase_norm TEXT NOT NULL,
                    source_phrase TEXT NOT NULL,
                    source_phrase_norm TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    relation_type TEXT NOT NULL DEFAULT 'direct-paraphrase',
                    status TEXT NOT NULL DEFAULT 'learning',
                    confidence REAL NOT NULL DEFAULT 0,
                    occurrence_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, question_phrase_norm, source_phrase_norm)
                );
                CREATE INDEX IF NOT EXISTS idx_paraphrase_items_user_updated
                    ON paraphrase_items(user_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS paraphrase_sources (
                    id TEXT PRIMARY KEY,
                    paraphrase_id TEXT NOT NULL,
                    source_key TEXT NOT NULL,
                    source_session_id TEXT,
                    source_question_id TEXT,
                    test_id TEXT,
                    test_title TEXT,
                    part_number INTEGER,
                    question_number TEXT,
                    question_prompt TEXT,
                    user_answer TEXT,
                    correct_answer TEXT,
                    evidence TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(paraphrase_id, source_key),
                    FOREIGN KEY(paraphrase_id) REFERENCES paraphrase_items(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_paraphrase_sources_item_created
                    ON paraphrase_sources(paraphrase_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS paraphrase_exports (
                    user_id TEXT NOT NULL,
                    paraphrase_id TEXT NOT NULL,
                    exported_at TEXT NOT NULL,
                    content_fingerprint TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(user_id, paraphrase_id),
                    FOREIGN KEY(paraphrase_id) REFERENCES paraphrase_items(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_paraphrase_exports_user
                    ON paraphrase_exports(user_id, exported_at DESC);

                CREATE TABLE IF NOT EXISTS vocabulary_smart_sync (
                    user_id TEXT NOT NULL,
                    vocabulary_id TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    content_fingerprint TEXT NOT NULL,
                    synced_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, vocabulary_id, destination),
                    FOREIGN KEY(vocabulary_id) REFERENCES vocabulary_items(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_vocabulary_smart_sync_user
                    ON vocabulary_smart_sync(user_id, destination, synced_at DESC);

                CREATE TABLE IF NOT EXISTS paraphrase_smart_sync (
                    user_id TEXT NOT NULL,
                    paraphrase_id TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    content_fingerprint TEXT NOT NULL,
                    synced_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, paraphrase_id, destination),
                    FOREIGN KEY(paraphrase_id) REFERENCES paraphrase_items(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_paraphrase_smart_sync_user
                    ON paraphrase_smart_sync(user_id, destination, synced_at DESC);
                """
            )
            vocabulary_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(vocabulary_items)").fetchall()
            }
            if "manual_capture_count" not in vocabulary_columns:
                connection.execute(
                    "ALTER TABLE vocabulary_items ADD COLUMN manual_capture_count "
                    "INTEGER NOT NULL DEFAULT 0"
                )
                connection.execute(
                    """
                    UPDATE vocabulary_items
                    SET manual_capture_count = (
                        SELECT COUNT(*)
                        FROM vocabulary_sources
                        WHERE vocabulary_sources.vocabulary_id = vocabulary_items.id
                          AND vocabulary_sources.source_type = 'manual'
                    )
                    """
                )
            paraphrase_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(paraphrase_items)").fetchall()
            }
            if "relation_type" not in paraphrase_columns:
                connection.execute(
                    "ALTER TABLE paraphrase_items ADD COLUMN relation_type "
                    "TEXT NOT NULL DEFAULT 'direct-paraphrase'"
                )
            vocabulary_export_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(vocabulary_exports)").fetchall()
            }
            if "content_fingerprint" not in vocabulary_export_columns:
                connection.execute(
                    "ALTER TABLE vocabulary_exports ADD COLUMN content_fingerprint "
                    "TEXT NOT NULL DEFAULT ''"
                )
            paraphrase_export_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(paraphrase_exports)").fetchall()
            }
            if "content_fingerprint" not in paraphrase_export_columns:
                connection.execute(
                    "ALTER TABLE paraphrase_exports ADD COLUMN content_fingerprint "
                    "TEXT NOT NULL DEFAULT ''"
                )

    @staticmethod
    def _content_fingerprint(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def vocabulary_fingerprint(cls, item: dict[str, Any]) -> str:
        return cls._content_fingerprint(
            {
                "term": item.get("term"),
                "meaning": item.get("meaning"),
                "note": item.get("note"),
                "status": item.get("status"),
                "occurrence_count": item.get("occurrence_count"),
                "manual_capture_count": item.get("manual_capture_count"),
                "sources": [
                    {
                        key: source.get(key)
                        for key in (
                            "source_type", "source_sentence", "source_context",
                            "source_session_id", "source_question_id", "test_id",
                            "test_title", "part_number",
                        )
                    }
                    for source in item.get("sources") or []
                ],
            }
        )

    @classmethod
    def paraphrase_fingerprint(cls, item: dict[str, Any]) -> str:
        return cls._content_fingerprint(
            {
                "question_phrase": item.get("question_phrase"),
                "source_phrase": item.get("source_phrase"),
                "note": item.get("note"),
                "relation_type": item.get("relation_type"),
                "status": item.get("status"),
                "confidence": item.get("confidence"),
                "occurrence_count": item.get("occurrence_count"),
                "sources": [
                    {
                        key: source.get(key)
                        for key in (
                            "source_session_id", "source_question_id", "test_id",
                            "test_title", "part_number", "question_number",
                            "question_prompt", "user_answer", "correct_answer", "evidence",
                        )
                    }
                    for source in item.get("sources") or []
                ],
            }
        )

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
            "SELECT exported_at, content_fingerprint FROM vocabulary_exports "
            "WHERE user_id = ? AND vocabulary_id = ?",
            (row["user_id"], row["id"]),
        ).fetchone()
        item = {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "term": str(row["term"]),
            "meaning": str(row["meaning"] or ""),
            "note": str(row["note"] or ""),
            "status": str(row["status"]),
            "occurrence_count": int(row["occurrence_count"] or 0),
            "manual_capture_count": int(row["manual_capture_count"] or 0),
            "sources": [self._source_from_row(source) for source in sources],
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "deduplicated": deduplicated,
            "source_added": source_added,
        }
        fingerprint = self.vocabulary_fingerprint(item)
        stored_fingerprint = str(export_row["content_fingerprint"] or "") if export_row else ""
        item["exported_before"] = bool(
            export_row and (not stored_fingerprint or stored_fingerprint == fingerprint)
        )
        item["last_exported_at"] = str(export_row["exported_at"]) if export_row else None
        return item

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
        source_type = str(payload.get("source_type") or "manual").strip()
        manual_capture_increment = 1 if source_type == "manual" else 0
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
                    "UPDATE vocabulary_items SET meaning = ?, note = ?, "
                    "manual_capture_count = manual_capture_count + ?, updated_at = ? WHERE id = ?",
                    (next_meaning, next_note, manual_capture_increment, now, item_id),
                )
            else:
                item_id = uuid.uuid4().hex
                connection.execute(
                    """
                    INSERT INTO vocabulary_items (
                        id, user_id, term, term_norm, meaning, note,
                        status, occurrence_count, manual_capture_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'learning', 0, ?, ?, ?)
                    """,
                    (
                        item_id, user_id, term, term_norm, meaning, note,
                        manual_capture_increment, now, now,
                    ),
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
                    source_type,
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
        marked = 0
        with self._connect() as connection:
            for item_id in ids:
                row = connection.execute(
                    "SELECT * FROM vocabulary_items WHERE user_id = ? AND id = ?",
                    (user_id, item_id),
                ).fetchone()
                if not row:
                    continue
                fingerprint = self.vocabulary_fingerprint(self._item_from_row(connection, row))
                connection.execute(
                    """
                    INSERT INTO vocabulary_exports (
                        user_id, vocabulary_id, exported_at, content_fingerprint
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, vocabulary_id)
                    DO UPDATE SET exported_at = excluded.exported_at,
                                  content_fingerprint = excluded.content_fingerprint
                    """,
                    (user_id, item_id, now, fingerprint),
                )
                marked += 1
            connection.commit()
        return marked

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

    @staticmethod
    def _paraphrase_source_key(payload: dict[str, Any]) -> str:
        parts = [
            str(payload.get("source_session_id") or "").strip(),
            str(payload.get("source_question_id") or "").strip(),
            str(payload.get("question_prompt") or "").strip(),
            str(payload.get("evidence") or "").strip(),
            str(payload.get("user_answer") or "").strip(),
            str(payload.get("correct_answer") or "").strip(),
        ]
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    @staticmethod
    def _paraphrase_source_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "source_session_id": row["source_session_id"],
            "source_question_id": row["source_question_id"],
            "test_id": row["test_id"],
            "test_title": row["test_title"],
            "part_number": row["part_number"],
            "question_number": row["question_number"],
            "question_prompt": row["question_prompt"],
            "user_answer": row["user_answer"],
            "correct_answer": row["correct_answer"],
            "evidence": row["evidence"],
            "created_at": str(row["created_at"]),
        }

    def _paraphrase_from_row(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        deduplicated: bool = False,
        source_added: bool = False,
    ) -> dict[str, Any]:
        sources = connection.execute(
            "SELECT * FROM paraphrase_sources WHERE paraphrase_id = ? "
            "ORDER BY created_at DESC, id",
            (row["id"],),
        ).fetchall()
        export_row = connection.execute(
            "SELECT exported_at, content_fingerprint FROM paraphrase_exports "
            "WHERE user_id = ? AND paraphrase_id = ?",
            (row["user_id"], row["id"]),
        ).fetchone()
        item = {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "question_phrase": str(row["question_phrase"]),
            "source_phrase": str(row["source_phrase"]),
            "note": str(row["note"] or ""),
            "relation_type": str(row["relation_type"] or "direct-paraphrase"),
            "status": str(row["status"]),
            "confidence": float(row["confidence"] or 0),
            "occurrence_count": int(row["occurrence_count"] or 0),
            "sources": [self._paraphrase_source_from_row(source) for source in sources],
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "deduplicated": deduplicated,
            "source_added": source_added,
        }
        fingerprint = self.paraphrase_fingerprint(item)
        stored_fingerprint = str(export_row["content_fingerprint"] or "") if export_row else ""
        item["exported_before"] = bool(
            export_row and (not stored_fingerprint or stored_fingerprint == fingerprint)
        )
        item["last_exported_at"] = str(export_row["exported_at"]) if export_row else None
        return item

    def capture_paraphrase(
        self,
        *,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        question_phrase = _clean_text(payload.get("question_phrase"))
        source_phrase = _clean_text(payload.get("source_phrase"))
        question_norm = normalize_term(question_phrase)
        source_norm = normalize_term(source_phrase)
        if not question_norm or not source_norm:
            raise ValueError("question_phrase and source_phrase are required")
        note = str(payload.get("note") or "").strip()
        relation_type = str(
            payload.get("relation_type") or "direct-paraphrase"
        ).strip()
        if relation_type not in PARAPHRASE_RELATION_TYPES:
            relation_type = "direct-paraphrase"
        confidence = max(0.0, min(float(payload.get("confidence") or 0), 1.0))
        now = self._now()
        source_key = self._paraphrase_source_key(payload)

        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT * FROM paraphrase_items
                WHERE user_id = ? AND question_phrase_norm = ? AND source_phrase_norm = ?
                """,
                (user_id, question_norm, source_norm),
            ).fetchone()
            deduplicated = existing is not None
            if existing:
                item_id = str(existing["id"])
                next_note = str(existing["note"] or "") or note
                next_confidence = max(float(existing["confidence"] or 0), confidence)
                connection.execute(
                    """
                    UPDATE paraphrase_items
                    SET note = ?, relation_type = ?, confidence = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (next_note, relation_type, next_confidence, now, item_id),
                )
            else:
                item_id = uuid.uuid4().hex
                connection.execute(
                    """
                    INSERT INTO paraphrase_items (
                        id, user_id, question_phrase, question_phrase_norm,
                        source_phrase, source_phrase_norm, note, status,
                        relation_type, confidence, occurrence_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'learning', ?, ?, 0, ?, ?)
                    """,
                    (
                        item_id,
                        user_id,
                        question_phrase,
                        question_norm,
                        source_phrase,
                        source_norm,
                        note,
                        relation_type,
                        confidence,
                        now,
                        now,
                    ),
                )

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO paraphrase_sources (
                    id, paraphrase_id, source_key, source_session_id,
                    source_question_id, test_id, test_title, part_number,
                    question_number, question_prompt, user_answer, correct_answer,
                    evidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    item_id,
                    source_key,
                    str(payload.get("source_session_id") or "").strip() or None,
                    str(payload.get("source_question_id") or "").strip() or None,
                    str(payload.get("test_id") or "").strip() or None,
                    str(payload.get("test_title") or "").strip() or None,
                    int(payload["part_number"]) if payload.get("part_number") is not None else None,
                    str(payload.get("question_number") or "").strip() or None,
                    str(payload.get("question_prompt") or "").strip() or None,
                    str(payload.get("user_answer") or "").strip() or None,
                    str(payload.get("correct_answer") or "").strip() or None,
                    str(payload.get("evidence") or "").strip() or None,
                    now,
                ),
            )
            source_added = bool(cursor.rowcount)
            source_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM paraphrase_sources WHERE paraphrase_id = ?",
                    (item_id,),
                ).fetchone()[0]
            )
            connection.execute(
                "UPDATE paraphrase_items SET occurrence_count = ?, updated_at = ? WHERE id = ?",
                (source_count, now, item_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM paraphrase_items WHERE id = ?",
                (item_id,),
            ).fetchone()
            return self._paraphrase_from_row(
                connection,
                row,
                deduplicated=deduplicated,
                source_added=source_added,
            )

    def list_paraphrases(
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
            clauses.append(
                "(question_phrase_norm LIKE ? OR source_phrase_norm LIKE ? OR lower(note) LIKE ?)"
            )
            pattern = f"%{normalized_query}%"
            params.extend([pattern, pattern, pattern])
        if status in PARAPHRASE_STATUSES:
            clauses.append("status = ?")
            params.append(status)
        params.append(bounded)
        sql = (
            "SELECT * FROM paraphrase_items WHERE "
            + " AND ".join(clauses)
            + " ORDER BY updated_at DESC, question_phrase_norm LIMIT ?"
        )
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
            return [self._paraphrase_from_row(connection, row) for row in rows]

    def paraphrases_by_ids(self, *, user_id: str, item_ids: list[str]) -> list[dict[str, Any]]:
        ordered_ids = list(dict.fromkeys(str(item_id) for item_id in item_ids if item_id))
        if not ordered_ids:
            return []
        placeholders = ",".join("?" for _ in ordered_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM paraphrase_items WHERE user_id = ? AND id IN ({placeholders})",
                [user_id, *ordered_ids],
            ).fetchall()
            by_id = {
                str(row["id"]): self._paraphrase_from_row(connection, row)
                for row in rows
            }
        return [by_id[item_id] for item_id in ordered_ids if item_id in by_id]

    def mark_paraphrases_exported(self, *, user_id: str, item_ids: list[str]) -> int:
        ids = list(dict.fromkeys(str(item_id) for item_id in item_ids if item_id))
        if not ids:
            return 0
        now = self._now()
        marked = 0
        with self._connect() as connection:
            for item_id in ids:
                row = connection.execute(
                    "SELECT * FROM paraphrase_items WHERE user_id = ? AND id = ?",
                    (user_id, item_id),
                ).fetchone()
                if not row:
                    continue
                fingerprint = self.paraphrase_fingerprint(
                    self._paraphrase_from_row(connection, row)
                )
                connection.execute(
                    """
                    INSERT INTO paraphrase_exports (
                        user_id, paraphrase_id, exported_at, content_fingerprint
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, paraphrase_id)
                    DO UPDATE SET exported_at = excluded.exported_at,
                                  content_fingerprint = excluded.content_fingerprint
                    """,
                    (user_id, item_id, now, fingerprint),
                )
                marked += 1
            connection.commit()
        return marked

    def prepare_smart_sync(
        self,
        *,
        user_id: str,
        destination: str = "ielts-vocab-local",
    ) -> dict[str, list[dict[str, Any]]]:
        with self._connect() as connection:
            word_rows = connection.execute(
                "SELECT * FROM vocabulary_items WHERE user_id = ? "
                "ORDER BY updated_at DESC, term_norm",
                (user_id,),
            ).fetchall()
            paraphrase_rows = connection.execute(
                "SELECT * FROM paraphrase_items WHERE user_id = ? "
                "ORDER BY updated_at DESC, question_phrase_norm",
                (user_id,),
            ).fetchall()
            words: list[dict[str, Any]] = []
            paraphrases: list[dict[str, Any]] = []
            for row in word_rows:
                item = self._item_from_row(connection, row)
                fingerprint = self.vocabulary_fingerprint(item)
                sync_row = connection.execute(
                    "SELECT content_fingerprint FROM vocabulary_smart_sync "
                    "WHERE user_id = ? AND vocabulary_id = ? AND destination = ?",
                    (user_id, item["id"], destination),
                ).fetchone()
                if not sync_row or str(sync_row["content_fingerprint"] or "") != fingerprint:
                    words.append({**item, "content_fingerprint": fingerprint})
            for row in paraphrase_rows:
                item = self._paraphrase_from_row(connection, row)
                fingerprint = self.paraphrase_fingerprint(item)
                sync_row = connection.execute(
                    "SELECT content_fingerprint FROM paraphrase_smart_sync "
                    "WHERE user_id = ? AND paraphrase_id = ? AND destination = ?",
                    (user_id, item["id"], destination),
                ).fetchone()
                if not sync_row or str(sync_row["content_fingerprint"] or "") != fingerprint:
                    paraphrases.append({**item, "content_fingerprint": fingerprint})
            return {"words": words, "paraphrases": paraphrases}

    def acknowledge_smart_sync(
        self,
        *,
        user_id: str,
        words: list[dict[str, str]],
        paraphrases: list[dict[str, str]],
        destination: str = "ielts-vocab-local",
    ) -> dict[str, Any]:
        word_ids: list[str] = []
        paraphrase_ids: list[str] = []
        stale_word_ids: list[str] = []
        stale_paraphrase_ids: list[str] = []
        for receipt in words:
            item_id = str(receipt.get("id") or "")
            item = self.get_item(user_id=user_id, item_id=item_id)
            if item and self.vocabulary_fingerprint(item) == str(receipt.get("fingerprint") or ""):
                word_ids.append(item_id)
            elif item_id:
                stale_word_ids.append(item_id)
        for receipt in paraphrases:
            item_id = str(receipt.get("id") or "")
            found = self.paraphrases_by_ids(user_id=user_id, item_ids=[item_id])
            if found and self.paraphrase_fingerprint(found[0]) == str(receipt.get("fingerprint") or ""):
                paraphrase_ids.append(item_id)
            elif item_id:
                stale_paraphrase_ids.append(item_id)
        now = self._now()
        with self._connect() as connection:
            for item_id in word_ids:
                item = self.get_item(user_id=user_id, item_id=item_id)
                if not item:
                    continue
                connection.execute(
                    """
                    INSERT INTO vocabulary_smart_sync (
                        user_id, vocabulary_id, destination, content_fingerprint, synced_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, vocabulary_id, destination)
                    DO UPDATE SET content_fingerprint = excluded.content_fingerprint,
                                  synced_at = excluded.synced_at
                    """,
                    (user_id, item_id, destination, self.vocabulary_fingerprint(item), now),
                )
            for item_id in paraphrase_ids:
                found = self.paraphrases_by_ids(user_id=user_id, item_ids=[item_id])
                if not found:
                    continue
                connection.execute(
                    """
                    INSERT INTO paraphrase_smart_sync (
                        user_id, paraphrase_id, destination, content_fingerprint, synced_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, paraphrase_id, destination)
                    DO UPDATE SET content_fingerprint = excluded.content_fingerprint,
                                  synced_at = excluded.synced_at
                    """,
                    (user_id, item_id, destination, self.paraphrase_fingerprint(found[0]), now),
                )
            connection.commit()
        self.mark_exported(user_id=user_id, item_ids=word_ids)
        self.mark_paraphrases_exported(user_id=user_id, item_ids=paraphrase_ids)
        return {
            "words_marked": len(word_ids),
            "paraphrases_marked": len(paraphrase_ids),
            "stale_word_ids": stale_word_ids,
            "stale_paraphrase_ids": stale_paraphrase_ids,
        }

    def update_paraphrase_status(
        self,
        *,
        user_id: str,
        item_id: str,
        status: str,
    ) -> dict[str, Any] | None:
        if status not in PARAPHRASE_STATUSES:
            raise ValueError("Unsupported paraphrase status")
        now = self._now()
        with self._connect() as connection:
            current = connection.execute(
                "SELECT * FROM paraphrase_items WHERE user_id = ? AND id = ?",
                (user_id, item_id),
            ).fetchone()
            if not current:
                return None
            connection.execute(
                "UPDATE paraphrase_items SET status = ?, updated_at = ? WHERE user_id = ? AND id = ?",
                (status, now, user_id, item_id),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM paraphrase_items WHERE user_id = ? AND id = ?",
                (user_id, item_id),
            ).fetchone()
            return self._paraphrase_from_row(connection, row)
