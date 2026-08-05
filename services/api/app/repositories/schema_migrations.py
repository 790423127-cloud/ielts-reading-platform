from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


SCHEMA_MIGRATIONS_TABLE = "schema_migrations"
EXPECTED_COMPONENT_VERSIONS = {
    "ai_jobs": 1,
    "ai_teacher": 1,
    "learning_plan": 1,
    "review_feedback": 1,
    "sentences": 1,
    "sessions": 1,
    "teacher": 1,
    "vocabulary": 2,
}


@contextmanager
def component_schema_migration(
    database_path: str | Path,
    *,
    component: str,
    version: int,
) -> Iterator[sqlite3.Connection | None]:
    """Run one component schema migration once and record it atomically."""
    if not component.strip():
        raise ValueError("schema component is required")
    if version < 1:
        raise ValueError("schema version must be positive")

    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                component TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT version FROM schema_migrations WHERE component = ?",
            (component,),
        ).fetchone()
        current_version = int(row["version"]) if row else 0
        if current_version > version:
            raise RuntimeError(
                f"database schema for {component} is newer than this application "
                f"({current_version} > {version})"
            )
        if current_version == version:
            connection.rollback()
            yield None
            return

        yield connection
        connection.execute(
            """
            INSERT INTO schema_migrations (component, version, applied_at)
            VALUES (?, ?, ?)
            ON CONFLICT(component) DO UPDATE SET
                version = excluded.version,
                applied_at = excluded.applied_at
            """,
            (component, version, datetime.now(timezone.utc).isoformat()),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def schema_versions(database_path: str | Path) -> dict[str, int]:
    path = Path(database_path)
    if not path.is_file():
        return {}
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (SCHEMA_MIGRATIONS_TABLE,),
        ).fetchone()
        if not table:
            return {}
        return {
            str(row[0]): int(row[1])
            for row in connection.execute(
                "SELECT component, version FROM schema_migrations ORDER BY component"
            ).fetchall()
        }
    finally:
        connection.close()
