from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import shutil

from app.repositories.ai_job_repository import AiJobRepository
from app.repositories.ai_teacher_repository import AiTeacherRepository
from app.repositories.learning_plan_repository import LearningPlanRepository
from app.repositories.review_feedback_repository import ReviewFeedbackRepository
from app.repositories.schema_migrations import (
    EXPECTED_COMPONENT_VERSIONS,
    schema_versions,
)
from app.repositories.sentence_repository import SentenceRepository
from app.repositories.session_repository import SQLiteSessionRepository
from app.repositories.teacher_repository import TeacherRepository
from app.repositories.vocabulary_repository import VocabularyRepository


def default_database_path() -> Path:
    return Path(
        os.getenv(
            "SESSION_DB_PATH",
            str(Path(__file__).resolve().parents[1] / "data" / "sessions.sqlite3"),
        )
    )


def pending_components(database_path: str | Path) -> list[str]:
    current = schema_versions(database_path)
    return [
        component
        for component, target in EXPECTED_COMPONENT_VERSIONS.items()
        if current.get(component, 0) < target
    ]


def backup_before_migration(database_path: str | Path) -> Path | None:
    path = Path(database_path)
    if not path.is_file() or not pending_components(path):
        return None
    backup_dir = Path(
        os.getenv(
            "SCHEMA_BACKUP_DIR",
            str(Path(__file__).resolve().parents[3] / "tmp" / "local-runtime"),
        )
    )
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"sessions.before-schema-migration.{stamp}.sqlite3"
    shutil.copy2(path, backup_path)
    return backup_path


def migrate_database(database_path: str | Path) -> dict[str, int]:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    for repository in (
        SQLiteSessionRepository,
        LearningPlanRepository,
        SentenceRepository,
        ReviewFeedbackRepository,
        VocabularyRepository,
        AiTeacherRepository,
        AiJobRepository,
        TeacherRepository,
    ):
        repository(path)
    versions = schema_versions(path)
    if versions != EXPECTED_COMPONENT_VERSIONS:
        raise RuntimeError(
            f"database schema versions are incomplete: {versions!r}"
        )
    return versions


def main() -> None:
    path = default_database_path()
    backup = backup_before_migration(path)
    versions = migrate_database(path)
    if backup:
        print(f"Schema backup: {backup}")
    print(f"Schema versions: {versions}")


if __name__ == "__main__":
    main()
