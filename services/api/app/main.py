from __future__ import annotations

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import settings


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    application.include_router(health_router, prefix="/api/v1")
    return application


app = create_app()
