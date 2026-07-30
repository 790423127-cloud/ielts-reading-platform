from __future__ import annotations

import json
import re
from typing import Any

from app.repositories.vocabulary_repository import VocabularyRepository
from app.services.ai_teacher import (
    AiTeacherNotConfiguredError,
    AiTeacherProviderError,
    generate_ai_reply,
)


MAX_WRONG_QUESTIONS = 40
MAX_PAIRS_PER_QUESTION = 5
MIN_CONFIDENCE = 0.72


def _clean_text(value: Any, *, limit: int = 500) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:limit]


def _contains_loose(haystack: str, needle: str) -> bool:
    hay = re.sub(r"\s+", " ", haystack).casefold()
    target = re.sub(r"\s+", " ", needle).casefold()
    return bool(target and target in hay)


def _json_object_from_answer(answer: str) -> dict[str, Any]:
    text = answer.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    return parsed if isinstance(parsed, dict) else {}


def _wrong_question_payload(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for question in result.get("wrong_questions") or []:
        evidence = question.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        evidence_rows = [
            _clean_text(item, limit=900)
            for item in evidence
            if _clean_text(item, limit=900)
        ][:4]
        rows.append(
            {
                "id": str(question.get("id") or ""),
                "number": str(question.get("number") or ""),
                "part_number": question.get("part_number"),
                "question_type": str(question.get("question_type") or ""),
                "prompt": _clean_text(question.get("prompt"), limit=900),
                "instructions": _clean_text(question.get("instructions"), limit=900),
                "options": question.get("options") or [],
                "user_answer": _clean_text(question.get("user_answer"), limit=300),
                "correct_answer": _clean_text(question.get("correct_answer"), limit=300),
                "paraphrasing": _clean_text(question.get("paraphrasing"), limit=900),
                "keywords": _clean_text(question.get("keywords"), limit=500),
                "evidence": evidence_rows,
            }
        )
        if len(rows) >= MAX_WRONG_QUESTIONS:
            break
    return rows


def extract_wrong_question_paraphrases(
    *,
    repository: VocabularyRepository,
    user_id: str,
    session_id: str,
    result: dict[str, Any],
    ai_reply_generator: Any = generate_ai_reply,
) -> dict[str, Any]:
    wrong_questions = _wrong_question_payload(result)
    if not wrong_questions:
        return {
            "status": "skipped",
            "reason": "no_wrong_questions",
            "wrong_question_count": 0,
            "candidate_count": 0,
            "saved_count": 0,
        }

    question = (
        "只处理错题。请从每道错题的题目表达和原文证据中提取 IELTS 阅读常见同义替换。"
        "只输出 JSON，不要解释。格式："
        '{"items":[{"question_id":"...","question_phrase":"题目中的表达",'
        '"source_phrase":"原文中的对应表达","note":"为什么等价/学生可能没识别出的点",'
        '"confidence":0.0}]}。'
        "规则：question_phrase 必须来自错题题目、选项或题目说明；"
        "source_phrase 必须来自原文证据中真实出现的表达；不要编造；不要处理正确题；"
        "每题最多 5 条；置信度低于 0.72 不要输出。"
    )
    context = {
        "test_id": result.get("test_id"),
        "test_title": result.get("test_title"),
        "session_id": session_id,
        "wrong_questions": wrong_questions,
    }
    try:
        generated = ai_reply_generator(
            question=question,
            context_type="wrong_question_paraphrase_extraction",
            context=context,
            history=[],
        )
        parsed = _json_object_from_answer(str(generated.get("answer") or ""))
    except AiTeacherNotConfiguredError:
        return {
            "status": "skipped",
            "reason": "ai_not_configured",
            "wrong_question_count": len(wrong_questions),
            "candidate_count": 0,
            "saved_count": 0,
        }
    except (AiTeacherProviderError, json.JSONDecodeError, ValueError) as error:
        return {
            "status": "failed",
            "reason": "ai_extraction_failed",
            "message": str(error),
            "wrong_question_count": len(wrong_questions),
            "candidate_count": 0,
            "saved_count": 0,
        }

    by_id = {row["id"]: row for row in wrong_questions}
    candidates = parsed.get("items") if isinstance(parsed, dict) else []
    if not isinstance(candidates, list):
        candidates = []

    saved_ids: list[str] = []
    skipped = 0
    per_question_count: dict[str, int] = {}
    for item in candidates:
        if not isinstance(item, dict):
            skipped += 1
            continue
        question_id = str(item.get("question_id") or "").strip()
        source_question = by_id.get(question_id)
        if not source_question:
            skipped += 1
            continue
        per_question_count[question_id] = per_question_count.get(question_id, 0) + 1
        if per_question_count[question_id] > MAX_PAIRS_PER_QUESTION:
            skipped += 1
            continue
        question_phrase = _clean_text(item.get("question_phrase"), limit=300)
        source_phrase = _clean_text(item.get("source_phrase"), limit=300)
        note = _clean_text(item.get("note"), limit=1200)
        try:
            confidence = float(item.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0
        evidence_text = "\n".join(source_question.get("evidence") or [])
        question_text = "\n".join(
            [
                str(source_question.get("prompt") or ""),
                str(source_question.get("instructions") or ""),
                json.dumps(source_question.get("options") or [], ensure_ascii=False),
            ]
        )
        if (
            confidence < MIN_CONFIDENCE
            or not question_phrase
            or not source_phrase
            or not _contains_loose(question_text, question_phrase)
            or not _contains_loose(evidence_text, source_phrase)
        ):
            skipped += 1
            continue
        saved = repository.capture_paraphrase(
            user_id=user_id,
            payload={
                "question_phrase": question_phrase,
                "source_phrase": source_phrase,
                "note": note,
                "confidence": confidence,
                "source_session_id": session_id,
                "source_question_id": question_id,
                "test_id": result.get("test_id"),
                "test_title": result.get("test_title"),
                "part_number": source_question.get("part_number"),
                "question_number": source_question.get("number"),
                "question_prompt": source_question.get("prompt"),
                "user_answer": source_question.get("user_answer"),
                "correct_answer": source_question.get("correct_answer"),
                "evidence": evidence_text,
            },
        )
        saved_ids.append(str(saved["id"]))

    return {
        "status": "completed",
        "reason": "wrong_questions_processed",
        "wrong_question_count": len(wrong_questions),
        "candidate_count": len(candidates),
        "saved_count": len(saved_ids),
        "skipped_count": skipped,
        "saved_ids": saved_ids,
    }
