from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.ability import router as ability_router
from app.api.ai_provider import router as ai_provider_router
from app.api.ai_jobs import router as ai_jobs_router
from app.api.ai_teacher import router as ai_teacher_router
from app.api.health import router as health_router
from app.api.learning_plan import router as learning_plan_router
from app.api.methods import router as methods_router
from app.api.personal_sentences import router as personal_sentences_router
from app.api.question_bank import router as question_bank_router
from app.api.review import router as review_router
from app.api.reports import router as reports_router
from app.api.sentence_training import router as sentence_training_router
from app.api.sessions import router as sessions_router
from app.api.vocabulary import router as vocabulary_router
from app.api.teacher import router as teacher_router
from app.core.config import settings
from app.core.logging import configure_logging


configure_logging()


def _safe_validation_errors(error: RequestValidationError) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in error.errors():
        rows.append({
            "loc": [str(part) for part in item.get("loc") or []],
            "msg": str(item.get("msg") or "Invalid value"),
            "type": str(item.get("type") or "validation_error"),
        })
    return rows


def _validation_message(errors: list[dict[str, Any]]) -> str:
    if not errors:
        return "请求参数校验失败。"
    first = errors[0]
    location = ".".join(part for part in first["loc"] if part not in {"body", "query", "path"})
    prefix = f"字段 {location}" if location else "请求参数"
    suffix = "；另有其他字段错误" if len(errors) > 1 else ""
    return f"{prefix}格式不正确：{first['msg']}{suffix}。"


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    @application.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        errors = _safe_validation_errors(error)
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "request_validation_failed",
                    "message": _validation_message(errors),
                    "errors": errors,
                }
            },
        )

    origins = [
        origin.strip()
        for origin in os.getenv(
            "WEB_ORIGINS",
            "http://127.0.0.1:8001,http://localhost:8001",
        ).split(",")
        if origin.strip()
    ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(question_bank_router, prefix="/api/v1")
    application.include_router(sessions_router, prefix="/api/v1")
    application.include_router(review_router, prefix="/api/v1")
    application.include_router(reports_router, prefix="/api/v1")
    application.include_router(methods_router, prefix="/api/v1")
    application.include_router(ability_router, prefix="/api/v1")
    application.include_router(learning_plan_router, prefix="/api/v1")
    application.include_router(sentence_training_router, prefix="/api/v1")
    application.include_router(personal_sentences_router, prefix="/api/v1")
    application.include_router(vocabulary_router, prefix="/api/v1")
    application.include_router(ai_provider_router, prefix="/api/v1")
    application.include_router(ai_jobs_router, prefix="/api/v1")
    application.include_router(ai_teacher_router, prefix="/api/v1")
    application.include_router(teacher_router, prefix="/api/v1")
    return application


app = create_app()
