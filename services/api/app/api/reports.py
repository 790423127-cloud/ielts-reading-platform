from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.sessions import session_repository
from app.domain.stage_report import build_stage_report
from app.services.report_documents import build_teacher_docx, build_teacher_pdf

router = APIRouter(prefix="/reports", tags=["reports"])


class SelectedReportRequest(BaseModel):
    user_id: str = Field(default="owner", min_length=1, max_length=120)
    session_ids: list[str] = Field(min_length=1, max_length=50)
    title: str = Field(default="IELTS G类阅读勾选汇总报告", min_length=1, max_length=200)


def _download_report(
    report: dict[str, Any],
    *,
    title: str,
    extension: Literal["pdf", "docx"],
) -> Response:
    payload = (
        build_teacher_pdf(report, title=title)
        if extension == "pdf"
        else build_teacher_docx(report, title=title)
    )
    media_type = (
        "application/pdf"
        if extension == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    fallback = f"ielts-reading-report.{extension}"
    filename = f"{title.strip() or 'IELTS阅读报告'}.{extension}"
    return Response(
        payload,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{fallback}\"; "
                f"filename*=UTF-8''{quote(filename)}"
            ),
            "Cache-Control": "private, no-store",
        },
    )


def _build_selected_report(payload: SelectedReportRequest) -> tuple[dict[str, Any], str]:
    session_ids = list(dict.fromkeys(
        session_id.strip() for session_id in payload.session_ids if session_id.strip()
    ))
    if not session_ids:
        raise HTTPException(status_code=422, detail="请至少选择一条练习记录")

    repository = session_repository()
    sessions = []
    missing_ids = []
    for session_id in session_ids:
        session = repository.get(user_id=payload.user_id, session_id=session_id)
        if session:
            sessions.append(session)
        else:
            missing_ids.append(session_id)
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "部分所选练习记录不存在或不属于当前用户",
                "missing_session_ids": missing_ids,
            },
        )

    title = payload.title.strip() or "IELTS G类阅读勾选汇总报告"
    report = build_stage_report(sessions)
    report["layout_type"] = "selected_sessions"
    report["layout_label"] = "勾选记录汇总报告"
    report["selected_session_ids"] = [session.id for session in sessions]
    report["summary"]["title"] = title
    report["data_notes"] = [
        *report.get("data_notes", []),
        f"本报告仅包含用户明确勾选的 {len(sessions)} 条练习记录。",
    ]
    return report, title


@router.get("/stage")
def stage_report(
    user_id: str = Query(default="owner", min_length=1, max_length=120),
    limit: int = Query(default=500, ge=1, le=1000),
) -> dict:
    sessions = session_repository().list_recent(user_id=user_id, limit=limit)
    return build_stage_report(sessions)


@router.get("/stage.{extension}")
def download_stage_report(
    extension: Literal["pdf", "docx"],
    user_id: str = Query(default="owner", min_length=1, max_length=120),
    limit: int = Query(default=500, ge=1, le=1000),
) -> Response:
    sessions = session_repository().list_recent(user_id=user_id, limit=limit)
    report = build_stage_report(sessions)
    if not report["summary"]["session_count"]:
        raise HTTPException(status_code=404, detail="No submitted sessions for report")
    return _download_report(
        report,
        title="IELTS G类阅读阶段学习报告",
        extension=extension,
    )


@router.post("/selection")
def selected_stage_report(payload: SelectedReportRequest) -> dict:
    report, _ = _build_selected_report(payload)
    return report


@router.post("/selection.{extension}")
def download_selected_stage_report(
    extension: Literal["pdf", "docx"],
    payload: SelectedReportRequest,
) -> Response:
    report, title = _build_selected_report(payload)
    return _download_report(report, title=title, extension=extension)


@router.get("/sessions/{session_id}.{extension}")
def download_session_report(
    session_id: str,
    extension: Literal["pdf", "docx"],
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> Response:
    session = session_repository().get(user_id=user_id, session_id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    report = build_stage_report([session])
    title = f"{session.result.get('test_title') or session.test_id}·单次练习报告"
    report["layout_type"] = "single_session"
    report["layout_label"] = "单次练习报告"
    report["summary"]["title"] = title
    return _download_report(report, title=title, extension=extension)
