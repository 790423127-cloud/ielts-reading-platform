from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
from typing import Any, Literal
import uuid

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.sessions import session_repository
from app.repositories.vocabulary_repository import VocabularyRepository

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])


class VocabularyCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    term: str = Field(min_length=1, max_length=300)
    meaning: str = Field(default="", max_length=4000)
    note: str = Field(default="", max_length=8000)
    source_type: Literal[
        "reading_text",
        "question",
        "option",
        "wrong_review",
        "sentence",
        "ai",
        "manual",
    ] = "manual"
    source_sentence: str | None = Field(default=None, max_length=8000)
    source_context: str | None = Field(default=None, max_length=12000)
    source_session_id: str | None = Field(default=None, max_length=120)
    source_question_id: str | None = Field(default=None, max_length=180)
    test_id: str | None = Field(default=None, max_length=120)
    test_title: str | None = Field(default=None, max_length=300)
    part_number: int | None = Field(default=None, ge=1, le=99)


class VocabularyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    meaning: str = Field(default="", max_length=4000)
    note: str = Field(default="", max_length=8000)
    status: Literal["learning", "mastered"] = "learning"


class VocabularySelectionExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    item_ids: list[str] = Field(default_factory=list, max_length=5000)
    only_unexported: bool = False


class ParaphraseSelectionExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    item_ids: list[str] = Field(default_factory=list, max_length=5000)
    only_unexported: bool = False
    format: Literal["txt", "json"] = "txt"


class ParaphraseUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    status: Literal["learning", "mastered"] = "learning"


class SmartSyncPrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)


class SmartSyncReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=180)
    fingerprint: str = Field(min_length=64, max_length=64)


class SmartSyncAcknowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(default="owner", min_length=1, max_length=120)
    transfer_id: str = Field(min_length=1, max_length=180)
    words: list[SmartSyncReceipt] = Field(default_factory=list, max_length=5000)
    paraphrases: list[SmartSyncReceipt] = Field(default_factory=list, max_length=5000)


def vocabulary_repository() -> VocabularyRepository:
    return VocabularyRepository(session_repository().database_path)


def _export_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        sources = item.get("sources") or []
        source_text = " | ".join(
            " · ".join(
                value
                for value in [
                    str(source.get("test_title") or "").strip(),
                    f"Part {source['part_number']}" if source.get("part_number") else "",
                    str(source.get("source_sentence") or source.get("source_context") or "").strip(),
                ]
                if value
            )
            for source in sources
        )
        rows.append(
            {
                "term": item["term"],
                "meaning": item["meaning"],
                "note": item["note"],
                "status": item["status"],
                "occurrence_count": item["occurrence_count"],
                "manual_capture_count": item["manual_capture_count"],
                "sources": source_text,
                "created_at": item["created_at"],
                "updated_at": item["updated_at"],
            }
        )
    return rows


def _spreadsheet_safe(value: Any) -> str:
    text = str(value or "")
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _paraphrase_export_line(item: dict[str, Any]) -> str:
    question_phrase = str(item.get("question_phrase") or "").strip()
    source_phrase = str(item.get("source_phrase") or "").strip()
    if not question_phrase or not source_phrase:
        return ""
    return f"{question_phrase} = {source_phrase}"


def _paraphrase_export_package(items: list[dict[str, Any]]) -> dict[str, Any]:
    exported_at = datetime.now(timezone.utc).isoformat()
    return {
        "schemaVersion": 1,
        "source": "ielts-reading-coach",
        "exportedAt": exported_at,
        "count": len(items),
        "items": [
            {
                "id": str(item["id"]),
                "questionPhrase": str(item.get("question_phrase") or "").strip(),
                "sourcePhrase": str(item.get("source_phrase") or "").strip(),
                "note": str(item.get("note") or "").strip(),
                "relationType": str(
                    item.get("relation_type") or "direct-paraphrase"
                ),
                "confidence": float(item.get("confidence") or 0),
                "occurrenceCount": int(item.get("occurrence_count") or 0),
                "createdAt": item.get("created_at"),
                "updatedAt": item.get("updated_at"),
                "sources": [
                    {
                        "id": str(source.get("id") or ""),
                        "testId": source.get("test_id"),
                        "testTitle": source.get("test_title"),
                        "partNumber": source.get("part_number"),
                        "questionNumber": source.get("question_number"),
                        "questionPrompt": source.get("question_prompt"),
                        "evidence": source.get("evidence"),
                        "userAnswer": source.get("user_answer"),
                        "correctAnswer": source.get("correct_answer"),
                    }
                    for source in item.get("sources") or []
                ],
            }
            for item in items
        ],
    }


def _smart_sync_package(pending: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    transfer_id = uuid.uuid4().hex
    words = [
        {
            "id": str(item["id"]),
            "fingerprint": str(item["content_fingerprint"]),
            "word": str(item.get("term") or "").strip(),
            "meaning": str(item.get("meaning") or "").strip(),
            "note": str(item.get("note") or "").strip(),
            "status": str(item.get("status") or "learning"),
            "occurrenceCount": int(item.get("occurrence_count") or 0),
            "manualCaptureCount": int(item.get("manual_capture_count") or 0),
            "createdAt": item.get("created_at"),
            "updatedAt": item.get("updated_at"),
            "sources": [
                {
                    "id": str(source.get("id") or ""),
                    "sourceType": source.get("source_type"),
                    "sentence": source.get("source_sentence"),
                    "context": source.get("source_context"),
                    "sessionId": source.get("source_session_id"),
                    "questionId": source.get("source_question_id"),
                    "testId": source.get("test_id"),
                    "testTitle": source.get("test_title"),
                    "partNumber": source.get("part_number"),
                }
                for source in item.get("sources") or []
            ],
        }
        for item in pending["words"]
        if str(item.get("term") or "").strip()
    ]
    paraphrases = _paraphrase_export_package(pending["paraphrases"])["items"]
    for index, item in enumerate(paraphrases):
        source = pending["paraphrases"][index]
        item["fingerprint"] = str(source["content_fingerprint"])
        item["status"] = str(source.get("status") or "learning")
    return {
        "type": "ielts-reading-coach-smart-sync",
        "schemaVersion": 1,
        "source": "ielts-reading-coach",
        "transferId": transfer_id,
        "preparedAt": datetime.now(timezone.utc).isoformat(),
        "words": words,
        "paraphrases": paraphrases,
        "counts": {"words": len(words), "paraphrases": len(paraphrases)},
    }


@router.get("")
def list_vocabulary(
    user_id: str = Query(default="owner", min_length=1, max_length=120),
    query: str = Query(default="", max_length=300),
    status: Literal["learning", "mastered"] | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    items = vocabulary_repository().list_items(
        user_id=user_id,
        query=query,
        status=status,
        limit=limit,
    )
    return {
        "count": len(items),
        "learning_count": sum(1 for item in items if item["status"] == "learning"),
        "mastered_count": sum(1 for item in items if item["status"] == "mastered"),
        "items": items,
        "export_formats": ["csv", "txt", "json"],
    }


@router.post("")
def capture_vocabulary(payload: VocabularyCaptureRequest) -> dict[str, Any]:
    try:
        return vocabulary_repository().capture(
            user_id=payload.user_id,
            payload=payload.model_dump(),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/export")
def export_vocabulary(
    format: Literal["csv", "txt", "json"] = Query(default="csv"),
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> Response:
    items = vocabulary_repository().list_items(user_id=user_id, limit=5000)
    rows = _export_rows(items)
    date_stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"ielts-vocabulary-{date_stamp}.{format}"

    if format == "json":
        body = json.dumps(
            {
                "version": 1,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "count": len(items),
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        )
        media_type = "application/json; charset=utf-8"
    elif format == "txt":
        body = "\n".join(
            term
            for row in rows
            if (term := str(row["term"] or "").strip())
        )
        media_type = "text/plain; charset=utf-8"
    else:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(["单词/词组", "中文释义", "个人笔记", "状态", "出现次数", "手动记录次数", "来源", "收藏时间", "更新时间"])
        for row in rows:
            writer.writerow(
                [
                    _spreadsheet_safe(row["term"]),
                    _spreadsheet_safe(row["meaning"]),
                    _spreadsheet_safe(row["note"]),
                    "已掌握" if row["status"] == "mastered" else "学习中",
                    row["occurrence_count"],
                    row["manual_capture_count"],
                    _spreadsheet_safe(row["sources"]),
                    row["created_at"],
                    row["updated_at"],
                ]
            )
        body = "\ufeff" + buffer.getvalue()
        media_type = "text/csv; charset=utf-8"

    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export")
def export_selected_vocabulary(payload: VocabularySelectionExportRequest) -> Response:
    repository = vocabulary_repository()
    items = (
        repository.items_by_ids(user_id=payload.user_id, item_ids=payload.item_ids)
        if payload.item_ids
        else repository.list_items(user_id=payload.user_id, limit=5000)
    )
    if payload.only_unexported:
        items = [item for item in items if not item["exported_before"]]
    if not items:
        raise HTTPException(status_code=409, detail="没有可导出的单词")

    terms = [str(item["term"]).strip() for item in items if str(item["term"]).strip()]
    body = "\n".join(terms)
    repository.mark_exported(
        user_id=payload.user_id,
        item_ids=[str(item["id"]) for item in items],
    )
    date_stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    scope = "unexported" if payload.only_unexported else "selected"
    return Response(
        content=body,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="ielts-vocabulary-{scope}-{date_stamp}.txt"'
            )
        },
    )


@router.get("/paraphrases")
def list_paraphrases(
    user_id: str = Query(default="owner", min_length=1, max_length=120),
    query: str = Query(default="", max_length=300),
    status: Literal["learning", "mastered"] | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    items = vocabulary_repository().list_paraphrases(
        user_id=user_id,
        query=query,
        status=status,
        limit=limit,
    )
    return {
        "count": len(items),
        "learning_count": sum(1 for item in items if item["status"] == "learning"),
        "mastered_count": sum(1 for item in items if item["status"] == "mastered"),
        "items": items,
        "export_formats": ["txt", "json"],
    }


@router.post("/paraphrases/export")
def export_selected_paraphrases(payload: ParaphraseSelectionExportRequest) -> Response:
    repository = vocabulary_repository()
    items = (
        repository.paraphrases_by_ids(user_id=payload.user_id, item_ids=payload.item_ids)
        if payload.item_ids
        else repository.list_paraphrases(user_id=payload.user_id, limit=5000)
    )
    if payload.only_unexported:
        items = [item for item in items if not item["exported_before"]]
    if not items:
        raise HTTPException(status_code=409, detail="没有可导出的同义替换")

    valid_items = [
        item
        for item in items
        if _paraphrase_export_line(item)
    ]
    if not valid_items:
        raise HTTPException(status_code=409, detail="没有可导出的同义替换")
    repository.mark_paraphrases_exported(
        user_id=payload.user_id,
        item_ids=[str(item["id"]) for item in valid_items],
    )
    date_stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    scope = "unexported" if payload.only_unexported else "selected"
    if payload.format == "json":
        body = json.dumps(
            _paraphrase_export_package(valid_items),
            ensure_ascii=False,
            indent=2,
        )
        media_type = "application/json; charset=utf-8"
        extension = "json"
    else:
        body = "\n".join(_paraphrase_export_line(item) for item in valid_items)
        media_type = "text/plain; charset=utf-8"
        extension = "txt"
    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="ielts-paraphrases-{scope}-{date_stamp}.{extension}"'
            )
        },
    )


@router.post("/sync/prepare")
def prepare_smart_sync(payload: SmartSyncPrepareRequest) -> dict[str, Any]:
    pending = vocabulary_repository().prepare_smart_sync(user_id=payload.user_id)
    return _smart_sync_package(pending)


@router.post("/sync/acknowledge")
def acknowledge_smart_sync(payload: SmartSyncAcknowledgeRequest) -> dict[str, Any]:
    result = vocabulary_repository().acknowledge_smart_sync(
        user_id=payload.user_id,
        words=[item.model_dump() for item in payload.words],
        paraphrases=[item.model_dump() for item in payload.paraphrases],
    )
    return {"transfer_id": payload.transfer_id, **result}


@router.put("/paraphrases/{item_id}")
def update_paraphrase(item_id: str, payload: ParaphraseUpdateRequest) -> dict[str, Any]:
    try:
        item = vocabulary_repository().update_paraphrase_status(
            user_id=payload.user_id,
            item_id=item_id,
            status=payload.status,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not item:
        raise HTTPException(status_code=404, detail="Paraphrase item not found")
    return item


@router.put("/{item_id}")
def update_vocabulary(item_id: str, payload: VocabularyUpdateRequest) -> dict[str, Any]:
    try:
        item = vocabulary_repository().update_item(
            user_id=payload.user_id,
            item_id=item_id,
            meaning=payload.meaning,
            note=payload.note,
            status=payload.status,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not item:
        raise HTTPException(status_code=404, detail="Vocabulary item not found")
    return item


@router.delete("/{item_id}")
def delete_vocabulary(
    item_id: str,
    user_id: str = Query(default="owner", min_length=1, max_length=120),
) -> dict[str, bool]:
    deleted = vocabulary_repository().delete_item(user_id=user_id, item_id=item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Vocabulary item not found")
    return {"deleted": True}
