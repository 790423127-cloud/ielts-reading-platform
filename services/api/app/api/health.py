from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str
    migrationPhase: str
    databaseConnected: bool
    features: dict[str, bool]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    # Importing and probing the application must not create or connect a database.
    return HealthResponse(
        ok=True,
        service=settings.app_name,
        version=settings.app_version,
        migrationPhase=settings.migration_phase,
        databaseConnected=False,
        features={
            "nextAppRouter": True,
            "sharedContracts": True,
            "legacyHashRouter": False,
            "deterministicScoringCore": True,
            "gtBandParity": True,
            "idempotentUserSessions": True,
            "scoringParity": True,
            "questionBankMigrated": True,
            "questionBankHashGuard": True,
            "realTestParityCases": True,
            "examWorkbench": True,
            "serverScoredSubmission": True,
            "fullMockTimer": True,
            "localDraftRestore": True,
            "sessionHistory": True,
        },
    )
