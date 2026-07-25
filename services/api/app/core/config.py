from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "IELTS Reading Platform API"
    app_version: str = "0.4.0"
    migration_phase: str = "exam_workbench_and_sessions"
    environment: str = os.getenv("APP_ENV", "development")


settings = Settings()
