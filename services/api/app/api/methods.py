from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.domain.method_courses import build_method_catalog, get_method_course
from app.domain.legacy_method_courses import (
    build_method_course_catalog,
    build_method_course_detail,
)

router = APIRouter(prefix="/methods", tags=["methods"])


@router.get("")
def list_methods() -> dict:
    current_catalog = build_method_catalog()
    foundation_courses = [item for item in current_catalog if item["kind"] == "foundation"]
    current_subtypes = {
        item["subtype"]: item
        for item in current_catalog
        if item["kind"] == "subtype"
    }
    legacy_courses = build_method_course_catalog()["courses"]
    subtype_courses = [
        {
            **current_subtypes.get(item["id"], {}),
            **item,
            "id": f"subtype-{item['id']}",
            "kind": "subtype",
            "subtype": item["id"],
            "objective": item["summary"],
        }
        for item in legacy_courses
    ]
    catalog = foundation_courses + subtype_courses
    return {
        "items": catalog,
        "foundation_count": sum(1 for item in catalog if item["kind"] == "foundation"),
        "subtype_count": sum(1 for item in catalog if item["kind"] == "subtype"),
        "ai_calls": 0,
    }


@router.get("/{course_id}")
def get_method(course_id: str) -> dict:
    if course_id.startswith("subtype-"):
        subtype = course_id.removeprefix("subtype-")
        try:
            detail = build_method_course_detail(subtype)
        except KeyError:
            detail = None
        if detail:
            return {
                **detail,
                "id": course_id,
                "kind": "subtype",
                "subtype": subtype,
                "objective": detail["summary"],
            }
    course = get_method_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Method course not found")
    return course
