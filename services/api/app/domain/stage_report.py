from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from app.repositories.session_repository import StoredSession

MIN_PRELIMINARY_SAMPLE = 5
MIN_STABLE_SAMPLE = 10

ERROR_CAUSE_LABELS = {
    "word_limit_exceeded": "超过词数限制",
    "multiple_choice_mismatch": "多选组合不完整",
    "answer_mismatch": "答案与标准答案不一致",
    "incorrect": "答案与标准答案不一致",
    "unanswered": "未作答",
}


def _accuracy(correct: int, total: int) -> float:
    return round(correct / total * 100, 1) if total else 0.0


def _status(total: int, accuracy: float) -> tuple[str, str, str]:
    if total < MIN_PRELIMINARY_SAMPLE:
        return "insufficient_data", "数据不足", "insufficient"
    if accuracy < 60:
        status, label = "weak", "薄弱"
    elif accuracy < 80:
        status, label = "developing", "提升中"
    else:
        status, label = "stable", "相对稳定"
    if total < MIN_STABLE_SAMPLE:
        label += "（初步）"
        sample_level = "preliminary"
    else:
        sample_level = "stable"
    return status, label, sample_level


def _field_value(question: dict[str, Any], field: str) -> str:
    if field == "source_part_number":
        return str(
            question.get("source_part_number")
            or question.get("part_number")
            or "未分类"
        )
    return str(question.get(field) or "未分类")


def _error_cause(question: dict[str, Any]) -> str:
    """Resolve cause text from stored answer data (no teaching advice)."""
    if not str(question.get("user_answer") or "").strip():
        return ERROR_CAUSE_LABELS["unanswered"]

    reasons = question.get("wrong_reasons")
    user_answer = str(question.get("user_answer") or "").strip()
    if isinstance(reasons, dict):
        for key in (user_answer, user_answer.upper(), user_answer.lower()):
            value = str(reasons.get(key) or "").strip()
            if value:
                return value
    elif isinstance(reasons, str):
        value = reasons.strip()
        if value:
            return value
    elif isinstance(reasons, list):
        for reason in reasons:
            value = str(reason or "").strip()
            if value:
                return value

    error_type = str(question.get("answer_error_type") or "").strip()
    if error_type:
        return ERROR_CAUSE_LABELS.get(error_type, error_type)
    return ERROR_CAUSE_LABELS["answer_mismatch"]


def _source_ref(question: dict[str, Any], result: dict[str, Any]) -> str:
    test_id = str(question.get("source_test_id") or result.get("test_id") or "")
    part = int(
        question.get("source_part_number")
        or question.get("part_number")
        or 0
    )
    question_id = str(
        question.get("source_question_id")
        or (
            str(question.get("id") or "").split(":", 2)[2]
            if str(question.get("id") or "").count(":") >= 2
            else question.get("id")
            or ""
        )
    )
    return f"{test_id}:{part}:{question_id}" if test_id and part and question_id else ""


def _timed_question(
    question: dict[str, Any],
    result: dict[str, Any],
    created_at: str,
) -> dict[str, Any] | None:
    elapsed_seconds = max(0, int(question.get("elapsed_seconds") or 0))
    if elapsed_seconds <= 0:
        return None
    return {
        "source_question_ref": _source_ref(question, result),
        "test_title": str(result.get("test_title") or result.get("test_id") or ""),
        "question_number": question.get("number"),
        "question_type": question.get("question_type")
        or question.get("question_subtype")
        or "未分类",
        "question_subtype": str(question.get("question_subtype") or "other"),
        "prompt": str(question.get("prompt") or ""),
        "user_answer": str(question.get("user_answer") or "未作答"),
        "correct_answer": str(question.get("correct_answer") or ""),
        "elapsed_seconds": elapsed_seconds,
        "is_correct": bool(question.get("is_correct")),
        "created_at": created_at,
    }


def _slowest_unique(
    candidates: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    for item in sorted(
        candidates,
        key=lambda row: (
            -int(row.get("elapsed_seconds") or 0),
            str(row.get("created_at") or ""),
            str(row.get("source_question_ref") or ""),
        ),
    ):
        ref = str(item.get("source_question_ref") or "")
        if ref and ref in seen_refs:
            continue
        if ref:
            seen_refs.add(ref)
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def _format_seconds_short(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    minutes, rem = divmod(seconds, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}小时{minutes}分"
    if minutes:
        return f"{minutes}分{rem}秒"
    return f"{rem}秒"


def _normalize_tfng_token(value: str) -> str:
    token = value.strip().upper().replace(" ", "").replace("_", "")
    if token in {"NG", "NOTGIVEN"}:
        return "NOT GIVEN"
    if token in {"T", "TRUE"}:
        return "TRUE"
    if token in {"F", "FALSE"}:
        return "FALSE"
    return token


def _tfng_confusion_stats(wrong_questions: list[dict[str, Any]]) -> dict[str, int]:
    stats = {
        "false_vs_not_given": 0,
        "true_vs_not_given": 0,
        "true_vs_false": 0,
        "other": 0,
        "total_tfng_wrong": 0,
    }
    for question in wrong_questions:
        if str(question.get("question_subtype") or "") != "true_false_not_given":
            continue
        stats["total_tfng_wrong"] += 1
        user = _normalize_tfng_token(str(question.get("user_answer") or ""))
        correct = _normalize_tfng_token(str(question.get("correct_answer") or ""))
        pair = {user, correct}
        if pair == {"FALSE", "NOT GIVEN"}:
            stats["false_vs_not_given"] += 1
        elif pair == {"TRUE", "NOT GIVEN"}:
            stats["true_vs_not_given"] += 1
        elif pair == {"TRUE", "FALSE"}:
            stats["true_vs_false"] += 1
        else:
            stats["other"] += 1
    return stats


def _aggregate(
    sessions: list[StoredSession],
    *,
    key_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], dict[str, Any]] = {}
    for session in sessions:
        for question in session.result.get("question_results") or []:
            values = tuple(_field_value(question, field) for field in key_fields)
            bucket = buckets.setdefault(
                values,
                {
                    field: value for field, value in zip(key_fields, values, strict=True)
                }
                | {"correct": 0, "total": 0, "elapsed_seconds": 0},
            )
            bucket["total"] += 1
            if question.get("is_correct"):
                bucket["correct"] += 1
            bucket["elapsed_seconds"] += max(0, int(question.get("elapsed_seconds") or 0))
    rows: list[dict[str, Any]] = []
    for bucket in buckets.values():
        accuracy = _accuracy(int(bucket["correct"]), int(bucket["total"]))
        status, status_label, sample_level = _status(int(bucket["total"]), accuracy)
        rows.append(
            {
                **bucket,
                "accuracy": accuracy,
                "status": status,
                "status_label": status_label,
                "sample_level": sample_level,
            }
        )
    # Lowest accuracy first for teacher scanning.
    rows.sort(key=lambda item: (item["accuracy"], -item["total"]))
    return rows


def _aggregate_part_elapsed(sessions: list[StoredSession]) -> dict[str, int]:
    """Sum part elapsed_seconds from session part_results when present."""
    totals: dict[str, int] = defaultdict(int)
    for session in sessions:
        for part in session.result.get("part_results") or []:
            key = str(part.get("part_number") or part.get("source_part_number") or "")
            if not key:
                continue
            totals[key] += max(0, int(part.get("elapsed_seconds") or 0))
    return dict(totals)


def build_stage_report(sessions: Iterable[StoredSession]) -> dict[str, Any]:
    rows = sorted(sessions, key=lambda row: row.created_at)
    total_questions = sum(int(row.result.get("total") or 0) for row in rows)
    total_correct = sum(int(row.result.get("score") or 0) for row in rows)
    total_seconds = sum(int(row.result.get("total_elapsed_seconds") or 0) for row in rows)
    total_unanswered = sum(
        1
        for row in rows
        for question in row.result.get("question_results") or []
        if not str(question.get("user_answer") or "").strip()
    )
    total_wrong = max(0, total_questions - total_correct - total_unanswered)

    configuration_attempts: defaultdict[tuple[Any, ...], int] = defaultdict(int)
    trend: list[dict[str, Any]] = []
    wrong_candidates: list[dict[str, Any]] = []
    timed_correct_candidates: list[dict[str, Any]] = []
    timed_wrong_candidates: list[dict[str, Any]] = []
    cause_buckets: dict[str, dict[str, Any]] = {}
    all_wrong_for_patterns: list[dict[str, Any]] = []

    for row in rows:
        result = row.result
        configuration = (
            row.test_id,
            str(result.get("practice_mode") or result.get("exam_mode") or ""),
            tuple(result.get("part_numbers") or []),
            str(result.get("skill_id") or ""),
        )
        configuration_attempts[configuration] += 1
        attempt_number = configuration_attempts[configuration]
        trend.append(
            {
                "session_id": row.id,
                "created_at": row.created_at,
                "test_id": row.test_id,
                "test_title": str(result.get("test_title") or row.test_id),
                "practice_mode": str(result.get("practice_mode") or "full_test"),
                "skill_label": result.get("skill_label"),
                "score": int(result.get("score") or 0),
                "total": int(result.get("total") or 0),
                "accuracy": float(result.get("accuracy") or 0),
                "elapsed_seconds": int(result.get("total_elapsed_seconds") or 0),
                "attempt_kind": "first" if attempt_number == 1 else "retry",
                "attempt_number": attempt_number,
            }
        )
        for question in result.get("question_results") or []:
            timed = _timed_question(question, result, row.created_at)
            if not timed:
                continue
            if timed["is_correct"]:
                timed_correct_candidates.append(timed)
            else:
                timed_wrong_candidates.append(timed)
        for question in result.get("wrong_questions") or []:
            all_wrong_for_patterns.append(question)
            evidence = question.get("evidence") or []
            if isinstance(evidence, str):
                evidence = [evidence] if evidence.strip() else []
            evidence_rows = [str(item) for item in evidence if str(item).strip()]
            location = str(question.get("location_analysis") or "").strip()
            cause_label = _error_cause(question)
            part_number = int(
                question.get("source_part_number")
                or question.get("part_number")
                or 0
            )
            question_number = question.get("number")
            source = " / ".join(
                value
                for value in (
                    str(result.get("test_title") or row.test_id),
                    f"Part {part_number}" if part_number else "",
                    f"Q{question_number}" if question_number is not None else "",
                )
                if value
            )
            wrong_candidates.append(
                {
                    "source_question_ref": _source_ref(question, result),
                    "test_title": str(result.get("test_title") or row.test_id),
                    "source": source,
                    "source_part_number": part_number,
                    "question_number": question_number,
                    "question_type": question.get("question_type")
                    or question.get("question_subtype")
                    or "未分类",
                    "question_subtype": str(
                        question.get("question_subtype") or "other"
                    ),
                    "prompt": str(question.get("prompt") or ""),
                    "user_answer": str(question.get("user_answer") or "未作答"),
                    "correct_answer": str(question.get("correct_answer") or ""),
                    "analysis": str(question.get("analysis") or question.get("reason") or ""),
                    "location_analysis": location,
                    "evidence": evidence_rows,
                    "cause_label": cause_label,
                    "student_confirmation_label": "未记录",
                    "elapsed_seconds": max(0, int(question.get("elapsed_seconds") or 0)),
                    "created_at": row.created_at,
                }
            )
            cause = cause_buckets.setdefault(
                cause_label,
                {
                    "label": cause_label,
                    "count": 0,
                    "session_ids": set(),
                    "examples": [],
                },
            )
            cause["count"] += 1
            cause["session_ids"].add(row.id)
            example = f"{result.get('test_title') or row.test_id} Q{question_number}"
            if example not in cause["examples"] and len(cause["examples"]) < 3:
                cause["examples"].append(example)

    type_matrix = _aggregate(rows, key_fields=("question_subtype", "question_type"))
    part_matrix = _aggregate(rows, key_fields=("source_part_number",))
    part_elapsed_map = _aggregate_part_elapsed(rows)
    for item in part_matrix:
        key = str(item.get("source_part_number") or "")
        # Prefer session part_results elapsed when available; else sum question timings.
        if key in part_elapsed_map and part_elapsed_map[key] > 0:
            item["elapsed_seconds"] = part_elapsed_map[key]

    # Sort parts by accuracy ascending (weakest first).
    part_matrix.sort(key=lambda item: (float(item["accuracy"]), -int(item["total"])))

    representative: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    for item in reversed(wrong_candidates):
        ref = str(item.get("source_question_ref") or "")
        if ref and ref in seen_refs:
            continue
        if ref:
            seen_refs.add(ref)
        representative.append(item)
        if len(representative) >= 8:
            break
    error_cause_distribution = [
        {
            "label": item["label"],
            "count": int(item["count"]),
            "session_count": len(item["session_ids"]),
            "examples": list(item["examples"]),
        }
        for item in sorted(
            cause_buckets.values(),
            key=lambda value: (-int(value["count"]), str(value["label"])),
        )
    ]

    overall_accuracy = _accuracy(total_correct, total_questions)
    slowest_correct = _slowest_unique(timed_correct_candidates, 3)
    slowest_wrong = _slowest_unique(timed_wrong_candidates, 5)
    tfng_confusion = _tfng_confusion_stats(all_wrong_for_patterns)

    band_hint = None
    if rows:
        latest = rows[-1].result or {}
        band = latest.get("band_estimate") or {}
        if isinstance(band, dict) and band.get("eligible"):
            band_hint = str(band.get("display_band") or band.get("estimated_band") or "")
        elif latest.get("estimated_gt_reading_band") is not None:
            band_hint = str(latest.get("estimated_gt_reading_band"))

    # Data-only summary bullets.
    insights: list[str] = []
    if rows:
        insights.append(
            f"共 {len(rows)} 次练习、{total_questions} 题："
            f"对 {total_correct} / 错 {total_wrong} / 未作答 {total_unanswered}，"
            f"正确率 {overall_accuracy}%。"
        )
        insights.append(f"合计用时 {_format_seconds_short(total_seconds)}。")
    if type_matrix:
        weakest = type_matrix[0]
        strongest = max(
            type_matrix, key=lambda item: (float(item["accuracy"]), int(item["total"]))
        )
        insights.append(
            f"题型正确率最低：{weakest['question_type']} "
            f"{weakest['accuracy']}%（{weakest['correct']}/{weakest['total']}，"
            f"样本 {weakest['total']} 题，{weakest['status_label']}）。"
        )
        if strongest is not weakest:
            insights.append(
                f"题型正确率最高：{strongest['question_type']} "
                f"{strongest['accuracy']}%（{strongest['correct']}/{strongest['total']}）。"
            )
    if part_matrix:
        weak_part = part_matrix[0]
        part_time = int(weak_part.get("elapsed_seconds") or 0)
        time_bit = f"，用时 {_format_seconds_short(part_time)}" if part_time else ""
        insights.append(
            f"Part 正确率最低：Part {weak_part['source_part_number']} "
            f"{weak_part['accuracy']}%（{weak_part['correct']}/{weak_part['total']}"
            f"{time_bit}）。"
        )
    if tfng_confusion["total_tfng_wrong"]:
        insights.append(
            "TRUE/FALSE/NOT GIVEN 混淆统计："
            f"FALSE↔NOT GIVEN {tfng_confusion['false_vs_not_given']} 题，"
            f"TRUE↔NOT GIVEN {tfng_confusion['true_vs_not_given']} 题，"
            f"TRUE↔FALSE {tfng_confusion['true_vs_false']} 题"
            f"（TFNG 错题共 {tfng_confusion['total_tfng_wrong']}）。"
        )
    if error_cause_distribution:
        top = error_cause_distribution[0]
        insights.append(
            f"出现最多的错因：{top['label']}（{top['count']} 题）。"
        )
    if slowest_wrong:
        longest = slowest_wrong[0]
        insights.append(
            f"最耗时错题：Q{longest['question_number']}，"
            f"{longest['elapsed_seconds']} 秒，"
            f"学生答 {longest['user_answer']}，正确 {longest['correct_answer']}。"
        )
    if len(trend) >= 2:
        change = round(trend[-1]["accuracy"] - trend[0]["accuracy"], 1)
        direction = "提高" if change > 0 else "下降" if change < 0 else "持平"
        insights.append(
            f"最近一次相对最早一次正确率{direction} {abs(change)} 个百分点。"
        )
    if band_hint:
        insights.append(f"练习参考 GT Band：{band_hint}（非官方成绩）。")

    time_notes: list[str] = []
    if total_questions and total_seconds:
        avg = int(total_seconds / max(total_questions, 1))
        time_notes.append(
            f"平均约 {avg} 秒/题（整卷 {_format_seconds_short(total_seconds)} / {total_questions} 题）。"
        )
    for item in part_matrix:
        elapsed = int(item.get("elapsed_seconds") or 0)
        if elapsed:
            time_notes.append(
                f"Part {item.get('source_part_number')} 用时 "
                f"{_format_seconds_short(elapsed)}，"
                f"正确率 {item.get('accuracy')}%（{item.get('correct')}/{item.get('total')}）。"
            )
    for item in slowest_wrong[:5]:
        time_notes.append(
            f"错题 Q{item.get('question_number')}（{item.get('question_type')}）"
            f" {item.get('elapsed_seconds')} 秒；"
            f"{item.get('user_answer')} → {item.get('correct_answer')}。"
        )
    if not time_notes:
        time_notes.append("当前记录缺少单题/Part 用时数据。")

    part_results = [
        {
            "title": (
                f"Part {item['source_part_number']}"
                if item["source_part_number"] != "未分类"
                else "未分类 Part"
            ),
            "correct": item["correct"],
            "total": item["total"],
            "accuracy": item["accuracy"],
            "status_label": item["status_label"],
            "sample_level": item["sample_level"],
            "elapsed_seconds": int(item.get("elapsed_seconds") or 0),
        }
        for item in part_matrix
    ]

    return {
        "report_type": "stage",
        "engine_version": "0.5.1-data",
        "layout_type": "stage",
        "layout_label": "阶段学习报告",
        "generated_from": "persisted_sessions",
        "ai_calls": 0,
        "summary": {
            "title": "阶段学习报告",
            "session_count": len(rows),
            "first_attempt_count": sum(
                1 for item in trend if item["attempt_kind"] == "first"
            ),
            "retry_count": sum(1 for item in trend if item["attempt_kind"] == "retry"),
            "correct": total_correct,
            "total_questions": total_questions,
            "wrong": total_wrong,
            "unanswered": total_unanswered,
            "accuracy": overall_accuracy,
            "total_elapsed_seconds": total_seconds,
            "date_from": rows[0].created_at if rows else None,
            "date_to": rows[-1].created_at if rows else None,
            "estimated_band": band_hint,
        },
        "trend": trend,
        "sessions": trend,
        "question_type_matrix": type_matrix,
        "part_matrix": part_matrix,
        "part_results": part_results,
        "error_cause_distribution": error_cause_distribution,
        "tfng_confusion_stats": tfng_confusion,
        "representative_questions": representative,
        "slowest_correct_questions": slowest_correct,
        "slowest_wrong_questions": slowest_wrong,
        "deterministic_interpretation": insights,
        "time_management_notes": time_notes,
        # Keep key for backward compatibility; content is data facts only.
        "teacher_observation_points": insights,
        "data_notes": [
            "本报告只汇总已提交练习的客观数据，不含教学方法建议。",
            "5–9 题为初步样本，10 题及以上较稳定；少于 5 题不作能力定性。",
            "首次与重做分开标记。",
            "单题用时仅统计带 timing 的提交；Part 用时优先取 part_results。",
            "参考 Band 仅为练习估算，不是官方成绩。",
        ],
    }
