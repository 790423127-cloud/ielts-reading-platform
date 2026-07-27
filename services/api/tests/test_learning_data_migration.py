from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "migrate_legacy_learning_data.py"
SPEC = importlib.util.spec_from_file_location("migrate_legacy_learning_data", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _legacy_database(path: Path) -> None:
    result = {
        "test_id": "b10-test-a",
        "test_title": "剑雅10 Test A",
        "score": 1,
        "total": 1,
        "question_results": [
            {
                "id": "b10-test-a-q1",
                "number": 1,
                "part_number": 1,
                "question_subtype": "true_false_not_given",
                "is_correct": True,
            }
        ],
        "wrong_questions": [],
    }
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY, test_id TEXT, test_title TEXT,
                created_at TEXT, score INTEGER, total INTEGER,
                total_seconds INTEGER, result_json TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "old-s1",
                "b10-test-a",
                "剑雅10 Test A",
                "2026-07-01T08:00:00+00:00",
                1,
                1,
                60,
                json.dumps(result, ensure_ascii=False),
            ),
        )
        connection.commit()


def test_learning_data_migration_is_preview_first_idempotent_and_reversible(
    tmp_path: Path,
) -> None:
    source = tmp_path / "old.db"
    destination = tmp_path / "new.db"
    manifest = tmp_path / "manifest.json"
    _legacy_database(source)

    preview = MODULE.preview_migration(source, destination)
    assert preview["source_sessions"] == 1
    assert preview["would_insert"] == 1
    assert not destination.exists()

    applied = MODULE.apply_migration(
        source,
        destination,
        user_id="owner",
        manifest_path=manifest,
    )
    assert applied["inserted_count"] == 1
    assert manifest.is_file()
    with sqlite3.connect(destination) as connection:
        row = connection.execute(
            "SELECT created_at, client_submission_id, result_json FROM sessions"
        ).fetchone()
    assert row[0] == "2026-07-01T08:00:00+00:00"
    assert row[1] == "legacy:old-s1"
    migrated_result = json.loads(row[2])
    assert migrated_result["migration_source"] == "legacy_progress_db"
    assert migrated_result["question_results"][0]["source_question_id"] == "b10-test-a-q1"

    repeated = MODULE.apply_migration(
        source,
        destination,
        user_id="owner",
        manifest_path=manifest,
    )
    assert repeated["inserted_count"] == 0
    assert repeated["already_imported"] == 1

    rollback_preview = MODULE.rollback_migration(manifest, apply=False)
    assert rollback_preview["would_delete"] == 1
    rolled_back = MODULE.rollback_migration(manifest, apply=True)
    assert rolled_back["deleted"] == 1
    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
