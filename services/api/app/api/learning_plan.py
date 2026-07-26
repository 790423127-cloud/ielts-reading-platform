from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.sessions import session_repository
from app.repositories.learning_plan_repository import LearningPlanRepository

router = APIRouter(prefix="/plan", tags=["learning-plan"])


@router.get("")
def get_learning_plan(
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> dict:
    sessions_repo = session_repository()
    sessions = sessions_repo.list_recent(user_id=user_id, limit=100)
    repository = LearningPlanRepository(sessions_repo.database_path)
    return repository.synchronize(user_id=user_id, sessions=sessions)


@router.get("/policy")
def get_learning_plan_policy() -> dict:
    return {
        "minimum_questions": 8,
        "required_success_days": 2,
        # 达标当天按第1天计算，第3天复习需间隔2个自然日。
        "review_delay_days": 2,
        "later_review_required": True,
        "manual_completion_allowed": False,
        "ai_can_mark_mastery": False,
    }
