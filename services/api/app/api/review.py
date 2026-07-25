from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.sessions import session_repository
from app.domain.review import build_wrong_question_review

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/wrong-questions")
def wrong_questions(
    user_id: str = Query(default="owner", min_length=1, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    sessions = session_repository().list_recent(user_id=user_id, limit=limit)
    items = build_wrong_question_review(sessions)
    return {
        "count": len(items),
        "items": items,
        "mastery_rule": "最近一次错误后连续答对2次才移出错题库",
    }
