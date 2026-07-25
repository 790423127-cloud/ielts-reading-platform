from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "IELTS Reading Platform API"
    app_version: str = "0.5.0"
    migration_phase: str = "review_methods_ability"
    environment: str = os.getenv("APP_ENV", "development")


settings = Settings()
