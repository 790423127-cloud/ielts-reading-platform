from __future__ import annotations

import sqlite3

import pytest

from app.db_migrate import migrate_database, pending_components
from app.repositories.schema_migrations import (
    EXPECTED_COMPONENT_VERSIONS,
    component_schema_migration,
    schema_versions,
)


def test_full_schema_migration_is_versioned_and_idempotent(tmp_path) -> None:
    database = tmp_path / "sessions.sqlite3"

    assert pending_components(database) == sorted(EXPECTED_COMPONENT_VERSIONS)
    first = migrate_database(database)
    second = migrate_database(database)

    assert first == EXPECTED_COMPONENT_VERSIONS
    assert second == EXPECTED_COMPONENT_VERSIONS
    assert pending_components(database) == []


def test_failed_component_migration_rolls_back_schema_and_version(tmp_path) -> None:
    database = tmp_path / "sessions.sqlite3"

    with pytest.raises(RuntimeError, match="stop migration"):
        with component_schema_migration(
            database,
            component="failing_component",
            version=1,
        ) as connection:
            assert connection is not None
            connection.execute("CREATE TABLE should_rollback (id TEXT PRIMARY KEY)")
            raise RuntimeError("stop migration")

    connection = sqlite3.connect(database)
    try:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='should_rollback'"
        ).fetchone()
    finally:
        connection.close()

    assert table is None
    assert "failing_component" not in schema_versions(database)
