from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ability import router as ability_router
from app.api.ai_teacher import router as ai_teacher_router
from app.api.health import router as health_router
from app.api.learning_plan import router as learning_plan_router
from app.api.methods import router as methods_router
from app.api.personal_sentences import router as personal_sentences_router
from app.api.question_bank import router as question_bank_router
from app.api.review import router as review_router
from app.api.sentence_training import router as sentence_training_router
from app.api.sessions import router as sessions_router
from app.api.vocabulary import router as vocabulary_router
from app.core.config import settings


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    origins = [
        origin.strip()
        for origin in os.getenv(
            "WEB_ORIGINS",
            "http://127.0.0.1:3000,http://localhost:3000",
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
    application.include_router(methods_router, prefix="/api/v1")
    application.include_router(ability_router, prefix="/api/v1")
    application.include_router(learning_plan_router, prefix="/api/v1")
    application.include_router(sentence_training_router, prefix="/api/v1")
    application.include_router(personal_sentences_router, prefix="/api/v1")
    application.include_router(vocabulary_router, prefix="/api/v1")
    application.include_router(ai_teacher_router, prefix="/api/v1")
    return application


app = create_app()
