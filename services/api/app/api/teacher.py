from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.sessions import session_repository
from app.domain.stage_report import build_stage_report
from app.repositories.teacher_repository import TeacherRepository

router = APIRouter(prefix="/teacher", tags=["teacher"])


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(default="owner", min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    due_at: str | None = Field(default=None, max_length=80)


class AssignmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(default="owner", min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    due_at: str | None = Field(default=None, max_length=80)
    status: Literal["active", "completed", "archived"] = "active"
    session_ids: list[str] = Field(default_factory=list, max_length=200)


def repository() -> TeacherRepository:
    sessions = session_repository()
    return TeacherRepository(sessions.database_path)


def assignment_report(user_id: str, assignment: dict[str, Any]) -> dict[str, Any]:
    sessions = []
    missing = []
    session_store = session_repository()
    for session_id in assignment.get("session_ids") or []:
        row = session_store.get(user_id=user_id, session_id=str(session_id))
        if row:
            sessions.append(row)
        else:
            missing.append(str(session_id))
    report = build_stage_report(sessions)
    report["report_type"] = "teacher_assignment"
    report["assignment"] = assignment
    report["missing_session_ids"] = missing
    report["data_notes"] = [
        *report.get("data_notes", []),
        "教师报告为确定性汇总，AI 调用为 0；教师需结合课堂观察给出最终判断。",
    ]
    return report


@router.get("/assignments")
def list_assignments(
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> dict[str, Any]:
    return {"items": repository().list_assignments(user_id)}


@router.post("/assignments")
def create_assignment(payload: AssignmentCreate) -> dict[str, Any]:
    return repository().create_assignment(
        payload.user_id,
        payload.title.strip(),
        payload.description.strip(),
        payload.due_at,
    )


@router.put("/assignments/{assignment_id}")
def update_assignment(assignment_id: str, payload: AssignmentUpdate) -> dict[str, Any]:
    known_sessions = {
        row.id
        for row in session_repository().list_recent(
            user_id=payload.user_id, limit=1000, include_archived=True
        )
    }
    unknown = sorted(set(payload.session_ids) - known_sessions)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={"code": "unknown_session_ids", "session_ids": unknown},
        )
    row = repository().update_assignment(
        payload.user_id,
        assignment_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        due_at=payload.due_at,
        status=payload.status,
        session_ids=payload.session_ids,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return row


@router.get("/assignments/{assignment_id}/report")
def get_assignment_report(
    assignment_id: str,
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> dict[str, Any]:
    assignment = repository().get_assignment(user_id, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment_report(user_id, assignment)


@router.post("/assignments/{assignment_id}/snapshots")
def create_snapshot(
    assignment_id: str,
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> dict[str, Any]:
    assignment = repository().get_assignment(user_id, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    report = assignment_report(user_id, assignment)
    return repository().create_snapshot(
        user_id, assignment_id, f"{assignment['title']}·教师报告", report
    )


@router.get("/report-snapshots")
def list_snapshots(
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> dict[str, Any]:
    return {"items": repository().list_snapshots(user_id)}
