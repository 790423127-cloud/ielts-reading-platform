from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.domain.method_courses import build_method_catalog, get_method_course

router = APIRouter(prefix="/methods", tags=["methods"])


@router.get("")
def list_methods() -> dict:
    catalog = build_method_catalog()
    return {
        "items": catalog,
        "foundation_count": sum(1 for item in catalog if item["kind"] == "foundation"),
        "subtype_count": sum(1 for item in catalog if item["kind"] == "subtype"),
        "ai_calls": 0,
    }


@router.get("/{course_id}")
def get_method(course_id: str) -> dict:
    course = get_method_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Method course not found")
    return course
