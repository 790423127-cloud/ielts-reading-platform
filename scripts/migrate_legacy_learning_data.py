from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any


LEGACY_INVENTORY_TABLES = (
    "sessions",
    "annotations",
    "question_stats",
    "skill_mastery",
    "learning_tasks",
    "task_attempts",
    "sentence_attempts",
    "sentence_skill_mastery",
    "teacher_assignments",
    "teacher_assignment_modules",
    "teacher_assignment_sessions",
    "teacher_report_snapshots",
    "ai_question_explanations",
    "ai_question_explanation_feedback",
    "ai_question_explanation_summaries",
    "ai_question_explanation_jobs",
    "ai_question_explanation_job_items",
    "error_cause_confirmations",
)
SUPPORTED_LEGACY_TABLES = {"sessions"}


def _connect_read_only(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _require_legacy_sessions(connection: sqlite3.Connection) -> None:
    tables = {
        str(row["name"])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "sessions" not in tables:
        raise ValueError("旧数据库中没有 sessions 表")
    required = {"id", "test_id", "created_at", "score", "total", "result_json"}
    missing = required - _table_columns(connection, "sessions")
    if missing:
        raise ValueError(f"旧 sessions 表缺少字段: {', '.join(sorted(missing))}")


def _legacy_inventory(connection: sqlite3.Connection) -> dict[str, Any]:
    available = {
        str(row["name"])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    counts = {
        table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        for table in LEGACY_INVENTORY_TABLES
        if table in available
    }
    unsupported_nonempty = {
        table: count
        for table, count in counts.items()
        if table not in SUPPORTED_LEGACY_TABLES and count > 0
    }
    return {
        "table_counts": counts,
        "supported_tables": sorted(SUPPORTED_LEGACY_TABLES),
        "unsupported_nonempty_tables": unsupported_nonempty,
        "cutover_ready": not unsupported_nonempty,
    }


def _load_result(row: sqlite3.Row) -> dict[str, Any]:
    try:
        result = json.loads(str(row["result_json"] or "{}"))
    except json.JSONDecodeError as error:
        raise ValueError(f"旧Session {row['id']} 的 result_json 无效") from error
    if not isinstance(result, dict):
        raise ValueError(f"旧Session {row['id']} 的 result_json 不是对象")
    result.setdefault("test_id", str(row["test_id"] or ""))
    result.setdefault("test_title", str(row["test_title"] or row["test_id"] or ""))
    result.setdefault("score", int(row["score"] or 0))
    result.setdefault("total", int(row["total"] or 0))
    if "total_elapsed_seconds" not in result and "total_seconds" in row.keys():
        result["total_elapsed_seconds"] = int(row["total_seconds"] or 0)
    for key in ("question_results", "wrong_questions"):
        for question in result.get(key) or []:
            if not isinstance(question, dict):
                continue
            raw_id = str(question.get("id") or "")
            question.setdefault("source_test_id", result.get("test_id"))
            question.setdefault(
                "source_part_number",
                question.get("part_number"),
            )
            question.setdefault(
                "source_question_id",
                raw_id.split(":", 2)[2] if raw_id.count(":") >= 2 else raw_id,
            )
    result["migration_source"] = "legacy_progress_db"
    return result


def _stable_import_id(source_session_id: str) -> str:
    digest = hashlib.sha256(source_session_id.encode("utf-8")).hexdigest()[:24]
    return f"legacy-{digest}"


def preview_migration(source_db: Path, destination_db: Path) -> dict[str, Any]:
    if not source_db.is_file():
        raise ValueError(f"旧数据库不存在: {source_db}")
    if source_db.resolve() == destination_db.resolve():
        raise ValueError("源数据库和目标数据库不能是同一个文件")
    with _connect_read_only(source_db) as source:
        _require_legacy_sessions(source)
        inventory = _legacy_inventory(source)
        rows = source.execute(
            "SELECT * FROM sessions ORDER BY created_at, id"
        ).fetchall()
        valid = 0
        invalid: list[dict[str, str]] = []
        for row in rows:
            try:
                _load_result(row)
                valid += 1
            except ValueError as error:
                invalid.append({"session_id": str(row["id"]), "error": str(error)})
    existing_clients: set[str] = set()
    if destination_db.is_file():
        with sqlite3.connect(destination_db) as destination:
            tables = {
                str(row[0])
                for row in destination.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            if "sessions" in tables:
                existing_clients = {
                    str(row[0])
                    for row in destination.execute(
                        "SELECT client_submission_id FROM sessions "
                        "WHERE client_submission_id LIKE 'legacy:%'"
                    ).fetchall()
                }
    duplicate_count = sum(
        1 for row in rows if f"legacy:{row['id']}" in existing_clients
    )
    return {
        "source_db": str(source_db.resolve()),
        "destination_db": str(destination_db.resolve()),
        "source_sessions": len(rows),
        "valid_sessions": valid,
        "invalid_sessions": invalid,
        "already_imported": duplicate_count,
        "would_insert": valid - duplicate_count,
        "source_inventory": inventory,
        "mode": "preview",
    }


def _ensure_destination_schema(connection: sqlite3.Connection) -> None:
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


def apply_migration(
    source_db: Path,
    destination_db: Path,
    *,
    user_id: str,
    manifest_path: Path,
    allow_partial: bool = False,
) -> dict[str, Any]:
    preview = preview_migration(source_db, destination_db)
    if preview["invalid_sessions"]:
        raise ValueError("存在无效旧Session；为防止部分迁移，未写入任何记录")

    unsupported = preview["source_inventory"]["unsupported_nonempty_tables"]
    if unsupported and not allow_partial:
        summary = ", ".join(f"{table}={count}" for table, count in unsupported.items())
        raise ValueError(
            "Legacy database contains non-empty tables that are not migrated; "
            f"partial migration refused: {summary}. "
            "Complete the mappings or explicitly use --allow-partial after backup approval."
        )

    previous_manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        previous_manifest = json.loads(manifest_path.read_text("utf-8"))
        if (
            Path(str(previous_manifest.get("source_db") or "")).resolve()
            != source_db.resolve()
            or Path(str(previous_manifest.get("destination_db") or "")).resolve()
            != destination_db.resolve()
        ):
            raise ValueError("现有迁移清单属于其他源或目标数据库，拒绝覆盖")

    destination_db.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path: Path | None = None
    if destination_db.is_file() and not previous_manifest.get("backup_path"):
        backup_path = destination_db.with_name(
            f"{destination_db.name}.backup-{timestamp}"
        )
        shutil.copy2(destination_db, backup_path)
    elif previous_manifest.get("backup_path"):
        backup_path = Path(str(previous_manifest["backup_path"]))

    inserted_ids: list[str] = []
    with _connect_read_only(source_db) as source:
        rows = source.execute(
            "SELECT * FROM sessions ORDER BY created_at, id"
        ).fetchall()
        with sqlite3.connect(destination_db) as destination:
            _ensure_destination_schema(destination)
            try:
                destination.execute("BEGIN")
                for row in rows:
                    source_id = str(row["id"])
                    imported_id = _stable_import_id(source_id)
                    client_id = f"legacy:{source_id}"
                    result = _load_result(row)
                    cursor = destination.execute(
                        """
                        INSERT OR IGNORE INTO sessions (
                            id, user_id, client_submission_id, test_id,
                            created_at, score, total, result_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            imported_id,
                            user_id,
                            client_id,
                            str(row["test_id"] or ""),
                            str(row["created_at"] or ""),
                            int(result.get("score") or 0),
                            int(result.get("total") or 0),
                            json.dumps(
                                result,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        ),
                    )
                    if cursor.rowcount:
                        inserted_ids.append(imported_id)
                destination.commit()
            except Exception:
                destination.rollback()
                raise

    all_inserted_ids = list(
        dict.fromkeys(
            [
                *[
                    str(value)
                    for value in previous_manifest.get("inserted_session_ids") or []
                ],
                *inserted_ids,
            ]
        )
    )
    manifest = {
        **preview,
        "mode": "applied",
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "partial_migration_accepted": bool(allow_partial and unsupported),
        "backup_path": str(backup_path) if backup_path else None,
        "inserted_count": len(inserted_ids),
        "total_inserted_count": len(all_inserted_ids),
        "inserted_session_ids": all_inserted_ids,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        "utf-8",
    )
    return {**manifest, "manifest_path": str(manifest_path.resolve())}


def rollback_migration(
    manifest_path: Path,
    *,
    apply: bool,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text("utf-8"))
    destination_db = Path(str(manifest["destination_db"])).resolve()
    inserted_ids = [str(value) for value in manifest.get("inserted_session_ids") or []]
    if not apply:
        return {
            "mode": "rollback_preview",
            "destination_db": str(destination_db),
            "would_delete": len(inserted_ids),
            "backup_path": manifest.get("backup_path"),
        }
    if not destination_db.is_file():
        raise ValueError(f"目标数据库不存在: {destination_db}")
    deleted = 0
    with sqlite3.connect(destination_db) as destination:
        try:
            destination.execute("BEGIN")
            for session_id in inserted_ids:
                cursor = destination.execute(
                    "DELETE FROM sessions WHERE id = ? AND client_submission_id LIKE 'legacy:%'",
                    (session_id,),
                )
                deleted += max(0, cursor.rowcount)
            destination.commit()
        except Exception:
            destination.rollback()
            raise
    return {
        "mode": "rolled_back",
        "destination_db": str(destination_db),
        "deleted": deleted,
        "backup_path": manifest.get("backup_path"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="安全预览或迁移旧版学习Session到新版SQLite数据库"
    )
    parser.add_argument("--source-db", type=Path)
    parser.add_argument("--destination-db", type=Path)
    parser.add_argument("--user-id", default="owner")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Explicitly accept migrating Sessions while other legacy data remains unsupported.",
    )
    parser.add_argument("--rollback-manifest", type=Path)
    args = parser.parse_args()

    if args.rollback_manifest:
        output = rollback_migration(args.rollback_manifest, apply=args.apply)
    else:
        if not args.source_db or not args.destination_db:
            parser.error("--source-db 和 --destination-db 必须同时提供")
        if args.apply:
            manifest_path = args.manifest or args.destination_db.with_name(
                "legacy-learning-migration-manifest.json"
            )
            output = apply_migration(
                args.source_db,
                args.destination_db,
                user_id=args.user_id,
                manifest_path=manifest_path,
                allow_partial=args.allow_partial,
            )
        else:
            output = preview_migration(args.source_db, args.destination_db)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
