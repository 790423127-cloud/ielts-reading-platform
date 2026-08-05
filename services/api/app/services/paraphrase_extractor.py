from __future__ import annotations

import json
import math
import re
import unicodedata
from typing import Any

from app.repositories.ai_teacher_repository import AiTeacherRepository
from app.repositories.vocabulary_repository import VocabularyRepository
from app.services.ai_teacher import (
    AiTeacherNotConfiguredError,
    AiTeacherProviderError,
    generate_ai_reply,
)


MAX_WRONG_QUESTIONS = 40
MAX_AI_WRONG_QUESTIONS = 8
MAX_PAIRS_PER_QUESTION = 5
MAX_PHRASE_WORDS = 8
MAX_PHRASE_CHARS = 120
MAX_ORDERED_GAP_TOKENS = 4
MIN_CONFIDENCE = 0.72
CURATED_CONFIDENCE = 1.0
PARAPHRASE_DELIMITERS = ("->", "→", "↔", "=>", "¡ת")
ALLOWED_RELATION_TYPES = {
    "direct-paraphrase",
    "near-paraphrase",
    "contextual-paraphrase",
    "curated-paraphrase",
}
REJECTED_RELATION_TYPES = {"logical-contrast", "evidence-only"}
_WORD_RE = re.compile(r"[\w£$%]+(?:['’\-][\w£$%]+)*", re.UNICODE)


def _unique_ids(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _clean_text(value: Any, *, limit: int = 500) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:limit]


def _clean_phrase(value: Any) -> str:
    text = _clean_text(value, limit=MAX_PHRASE_CHARS + 40)
    return text.strip(" \t\r\n\"'‘’“”.,!?;:，。！？；：")


def _normalized_tokens(value: str) -> list[str]:
    folded = unicodedata.normalize("NFKC", value).casefold()
    return [token for token in _WORD_RE.findall(folded) if token]


def _phrase_word_count(value: str) -> int:
    return len(_normalized_tokens(value))


def _is_atomic_phrase(value: str) -> bool:
    phrase = _clean_phrase(value)
    if not phrase or len(phrase) > MAX_PHRASE_CHARS:
        return False
    word_count = _phrase_word_count(phrase)
    if word_count < 1 or word_count > MAX_PHRASE_WORDS:
        return False
    lowered = phrase.casefold()
    return not any(marker in lowered for marker in (",", "，", ";", "；", "\n", " vs ", " versus "))


def _contains_loose(haystack: str, needle: str) -> bool:
    hay = " ".join(_normalized_tokens(haystack))
    target = " ".join(_normalized_tokens(needle))
    return bool(target and target in hay)


def _contains_ordered_gap(
    haystack: str,
    needle: str,
    *,
    max_inserted_tokens: int = MAX_ORDERED_GAP_TOKENS,
) -> bool:
    """Match a phrase whose words stay ordered with a small evidence-only gap.

    This covers cases such as "glow-worm caves have attracted" matching
    "glow-worm caves in New Zealand have attracted", without accepting a
    sentence assembled from distant words.
    """

    hay_tokens = _normalized_tokens(haystack)
    needle_tokens = _normalized_tokens(needle)
    if not hay_tokens or not needle_tokens or len(needle_tokens) > len(hay_tokens):
        return False
    for start, token in enumerate(hay_tokens):
        if token != needle_tokens[0]:
            continue
        position = start
        inserted = 0
        matched = True
        for expected in needle_tokens[1:]:
            next_position = position + 1
            while next_position < len(hay_tokens) and hay_tokens[next_position] != expected:
                inserted += 1
                if inserted > max_inserted_tokens:
                    matched = False
                    break
                next_position += 1
            if not matched or next_position >= len(hay_tokens):
                matched = False
                break
            position = next_position
        if matched:
            return True
    return False


def _contains_supported(haystack: str, needle: str) -> bool:
    return _contains_loose(haystack, needle) or _contains_ordered_gap(haystack, needle)


def _pair_validation_reason(
    question: dict[str, Any],
    question_phrase: str,
    source_phrase: str,
) -> str | None:
    if not _is_atomic_phrase(question_phrase) or not _is_atomic_phrase(source_phrase):
        return "not_atomic_or_over_length"
    if not _contains_supported(_question_text(question), question_phrase):
        return "question_phrase_not_supported"
    if not _contains_supported(_evidence_text(question), source_phrase):
        return "source_phrase_not_supported"
    return None


def _question_text(question: dict[str, Any]) -> str:
    return "\n".join(
        [
            str(question.get("prompt") or ""),
            str(question.get("instructions") or ""),
            json.dumps(question.get("options") or [], ensure_ascii=False),
        ]
    )


def _evidence_text(question: dict[str, Any]) -> str:
    evidence = question.get("evidence") or []
    if isinstance(evidence, str):
        return evidence
    return "\n".join(str(item) for item in evidence if str(item).strip())


def _curated_pairs(value: Any) -> list[tuple[str, str]]:
    text = _clean_text(value, limit=2400)
    if not text:
        return []
    lowered = text.casefold()
    if "no correspondence found" in lowered or "does not match" in lowered:
        return []
    pairs: list[tuple[str, str]] = []
    for segment in re.split(r"[;\n]+", text):
        for delimiter in PARAPHRASE_DELIMITERS:
            if delimiter not in segment:
                continue
            left, right = segment.split(delimiter, 1)
            left = _clean_phrase(left)
            right = _clean_phrase(right)
            if left and right:
                pairs.append((left, right))
            break
    return pairs[:MAX_PAIRS_PER_QUESTION]


def _save_pair(
    *,
    repository: VocabularyRepository,
    user_id: str,
    session_id: str,
    result: dict[str, Any],
    source_question: dict[str, Any],
    question_phrase: str,
    source_phrase: str,
    note: str,
    confidence: float,
    relation_type: str,
) -> str:
    saved = repository.capture_paraphrase(
        user_id=user_id,
        payload={
            "question_phrase": _clean_phrase(question_phrase),
            "source_phrase": _clean_phrase(source_phrase),
            "note": note,
            "confidence": confidence,
            "relation_type": relation_type,
            "source_session_id": session_id,
            "source_question_id": source_question.get("id"),
            "test_id": result.get("test_id"),
            "test_title": result.get("test_title"),
            "part_number": source_question.get("part_number"),
            "question_number": source_question.get("number"),
            "question_prompt": source_question.get("prompt"),
            "user_answer": source_question.get("user_answer"),
            "correct_answer": source_question.get("correct_answer"),
            "evidence": _evidence_text(source_question),
        },
    )
    return str(saved["id"])


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


def _ai_question(batch: list[dict[str, Any]]) -> str:
    return (
        "只处理下面这批错题，从题目表达和原文证据中提取 IELTS 阅读同义替换。"
        "只输出 JSON，不要解释。格式："
        '{"items":[{"question_id":"...","question_phrase":"题目中的短语",'
        '"source_phrase":"原文中的对应短语","relation_type":"direct-paraphrase",'
        '"note":"简短说明","confidence":0.0}]}。'
        "每侧优先 1-6 个词，绝对不超过 8 个词；一条只表达一个替换关系，禁止完整句、并列清单或拼接远距离词语。"
        "question_phrase 必须来自该题题干、选项或说明；source_phrase 必须来自该题原文证据，允许中间最多插入 4 个不改变关系的限定词。"
        "relation_type 只能是 direct-paraphrase、near-paraphrase 或 contextual-paraphrase。"
        "不要输出 logical-contrast、evidence-only 或仅靠推理成立的关系。每题最多 5 条，置信度低于 0.72 不输出。"
        f"本批共有 {len(batch)} 道错题。"
    )


def _process_ai_candidates(
    *,
    candidates: Any,
    questions: list[dict[str, Any]],
    repository: VocabularyRepository,
    user_id: str,
    session_id: str,
    result: dict[str, Any],
) -> tuple[list[str], int, int]:
    if not isinstance(candidates, list):
        return [], 0, 0
    by_id = {row["id"]: row for row in questions}
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
        question_phrase = _clean_phrase(item.get("question_phrase"))
        source_phrase = _clean_phrase(item.get("source_phrase"))
        note = _clean_text(item.get("note"), limit=1200)
        relation_type = _clean_text(item.get("relation_type") or "direct-paraphrase", limit=60)
        try:
            confidence = float(item.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0
        if (
            confidence < MIN_CONFIDENCE
            or relation_type in REJECTED_RELATION_TYPES
            or relation_type not in ALLOWED_RELATION_TYPES
            or _pair_validation_reason(source_question, question_phrase, source_phrase)
        ):
            skipped += 1
            continue
        saved_ids.append(
            _save_pair(
                repository=repository,
                user_id=user_id,
                session_id=session_id,
                result=result,
                source_question=source_question,
                question_phrase=question_phrase,
                source_phrase=source_phrase,
                note=note,
                confidence=confidence,
                relation_type=relation_type,
            )
        )
    return saved_ids, skipped, len(candidates)


def extract_wrong_question_paraphrases(
    *,
    repository: VocabularyRepository,
    user_id: str,
    session_id: str,
    result: dict[str, Any],
    ai_reply_generator: Any = generate_ai_reply,
    allow_ai: bool = True,
    max_ai_calls: int = 1,
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

    local_saved_ids: list[str] = []
    local_candidate_count = 0
    local_skipped_count = 0
    unresolved_questions: list[dict[str, Any]] = []
    for source_question in wrong_questions:
        saved_for_question = False
        pairs = _curated_pairs(source_question.get("paraphrasing"))
        local_candidate_count += len(pairs)
        for question_phrase, source_phrase in pairs:
            if _pair_validation_reason(source_question, question_phrase, source_phrase):
                local_skipped_count += 1
                continue
            local_saved_ids.append(
                _save_pair(
                    repository=repository,
                    user_id=user_id,
                    session_id=session_id,
                    result=result,
                    source_question=source_question,
                    question_phrase=question_phrase,
                    source_phrase=source_phrase,
                    note="题库已核验的题干与原文同义替换。",
                    confidence=CURATED_CONFIDENCE,
                    relation_type="curated-paraphrase",
                )
            )
            saved_for_question = True
        if not saved_for_question:
            unresolved_questions.append(source_question)

    local_saved_ids = _unique_ids(local_saved_ids)
    if not unresolved_questions:
        return {
            "status": "completed",
            "reason": "curated_paraphrases_saved",
            "wrong_question_count": len(wrong_questions),
            "candidate_count": local_candidate_count,
            "saved_count": len(local_saved_ids),
            "skipped_count": local_skipped_count,
            "local_saved_count": len(local_saved_ids),
            "ai_saved_count": 0,
            "ai_status": "not_needed",
            "ai_batches_completed": 0,
            "ai_batches_planned": 0,
            "saved_ids": local_saved_ids,
        }

    total_batches = math.ceil(len(unresolved_questions) / MAX_AI_WRONG_QUESTIONS)
    allowed_calls = max(0, int(max_ai_calls))
    ai_question_capacity = min(
        len(unresolved_questions), allowed_calls * MAX_AI_WRONG_QUESTIONS
    )
    if not allow_ai or allowed_calls == 0:
        return {
            "status": "queued",
            "reason": "ai_supplement_queued",
            "wrong_question_count": len(wrong_questions),
            "candidate_count": local_candidate_count,
            "saved_count": len(local_saved_ids),
            "skipped_count": local_skipped_count,
            "local_saved_count": len(local_saved_ids),
            "ai_saved_count": 0,
            "ai_status": "queued",
            "ai_batches_completed": 0,
            "ai_batches_planned": total_batches,
            "ai_question_count": ai_question_capacity,
            "ai_deferred_question_count": len(unresolved_questions),
            "saved_ids": local_saved_ids,
        }

    batches = [
        unresolved_questions[index : index + MAX_AI_WRONG_QUESTIONS]
        for index in range(0, ai_question_capacity, MAX_AI_WRONG_QUESTIONS)
    ]
    ai_saved_ids: list[str] = []
    ai_candidate_count = 0
    ai_skipped_count = 0
    completed_batches = 0
    processed_questions = 0
    provider_request_ids: list[str] = []
    ai_usage = {
        "ai_provider": None,
        "ai_model": None,
        "ai_input_tokens": 0,
        "ai_output_tokens": 0,
    }
    ai_status = "completed"
    reason = "local_and_ai_paraphrases_processed"
    error_message = ""

    for batch in batches:
        try:
            generated = ai_reply_generator(
                question=_ai_question(batch),
                context_type="wrong_question_paraphrase_extraction",
                context={
                    "test_id": result.get("test_id"),
                    "test_title": result.get("test_title"),
                    "session_id": session_id,
                    "wrong_questions": batch,
                },
                history=[],
            )
            provider = generated.get("provider")
            model = generated.get("model")
            input_tokens = int(generated.get("input_tokens") or 0)
            output_tokens = int(generated.get("output_tokens") or 0)
            request_id = str(generated.get("provider_request_id") or "").strip()
            ai_usage["ai_provider"] = provider or ai_usage["ai_provider"]
            ai_usage["ai_model"] = model or ai_usage["ai_model"]
            ai_usage["ai_input_tokens"] += input_tokens
            ai_usage["ai_output_tokens"] += output_tokens
            if request_id:
                provider_request_ids.append(request_id)
            AiTeacherRepository(repository.database_path).record_provider_event(
                user_id=user_id,
                purpose="wrong_question_paraphrase_extraction",
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                provider_request_id=request_id or None,
            )
            parsed = _json_object_from_answer(str(generated.get("answer") or ""))
        except AiTeacherNotConfiguredError:
            ai_status = "skipped"
            reason = "ai_not_configured"
            break
        except (AiTeacherProviderError, json.JSONDecodeError, ValueError) as error:
            ai_status = "failed"
            reason = "ai_extraction_failed"
            error_message = str(error)
            break

        saved, skipped, candidate_count = _process_ai_candidates(
            candidates=parsed.get("items") if isinstance(parsed, dict) else [],
            questions=batch,
            repository=repository,
            user_id=user_id,
            session_id=session_id,
            result=result,
        )
        ai_saved_ids.extend(saved)
        ai_skipped_count += skipped
        ai_candidate_count += candidate_count
        completed_batches += 1
        processed_questions += len(batch)

    raw_ai_saved_count = len(ai_saved_ids)
    ai_saved_ids = _unique_ids(ai_saved_ids)
    saved_ids = _unique_ids([*local_saved_ids, *ai_saved_ids])
    deferred = len(unresolved_questions) - processed_questions
    if ai_status == "completed" and deferred > 0:
        ai_status = "deferred_daily_limit"
        reason = "ai_daily_capacity_reached"
    status = "completed"
    if ai_status == "failed":
        status = "partial" if saved_ids else "failed"
    elif ai_status == "skipped":
        status = "partial" if saved_ids else "skipped"
    elif deferred > 0:
        status = "partial"

    summary = {
        "status": status,
        "reason": reason,
        "wrong_question_count": len(wrong_questions),
        "candidate_count": local_candidate_count + ai_candidate_count,
        "saved_count": len(saved_ids),
        "skipped_count": local_skipped_count + ai_skipped_count,
        "local_saved_count": len(local_saved_ids),
        "ai_saved_count": len(ai_saved_ids),
        "deduplicated_candidate_count": raw_ai_saved_count - len(ai_saved_ids),
        "ai_status": ai_status,
        "ai_batches_completed": completed_batches,
        "ai_batches_planned": total_batches,
        "ai_question_count": processed_questions,
        "ai_deferred_question_count": deferred,
        "ai_provider_request_ids": provider_request_ids,
        "saved_ids": saved_ids,
        **ai_usage,
    }
    if error_message:
        summary["message"] = error_message
    return summary
