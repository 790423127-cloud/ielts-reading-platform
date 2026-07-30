from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.api.sessions import session_repository
from app.domain.stage_report import build_stage_report
from app.services.report_documents import build_teacher_docx, build_teacher_pdf

router = APIRouter(prefix="/reports", tags=["reports"])


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
