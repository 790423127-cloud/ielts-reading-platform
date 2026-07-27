from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from app.repositories.session_repository import StoredSession

MIN_PRELIMINARY_SAMPLE = 5
MIN_STABLE_SAMPLE = 10


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


def _aggregate(
    sessions: list[StoredSession],
    *,
    key_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], dict[str, Any]] = {}
    for session in sessions:
        for question in session.result.get("question_results") or []:
            values = tuple(str(question.get(field) or "未分类") for field in key_fields)
            bucket = buckets.setdefault(
                values,
                {
                    field: value for field, value in zip(key_fields, values, strict=True)
                }
                | {"correct": 0, "total": 0},
            )
            bucket["total"] += 1
            if question.get("is_correct"):
                bucket["correct"] += 1
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
    rows.sort(key=lambda item: (item["accuracy"], -item["total"]))
    return rows


def build_stage_report(sessions: Iterable[StoredSession]) -> dict[str, Any]:
    rows = sorted(sessions, key=lambda row: row.created_at)
    total_questions = sum(int(row.result.get("total") or 0) for row in rows)
    total_correct = sum(int(row.result.get("score") or 0) for row in rows)
    total_seconds = sum(int(row.result.get("total_elapsed_seconds") or 0) for row in rows)

    configuration_attempts: defaultdict[tuple[Any, ...], int] = defaultdict(int)
    trend: list[dict[str, Any]] = []
    wrong_candidates: list[dict[str, Any]] = []
    timed_correct_candidates: list[dict[str, Any]] = []
    timed_wrong_candidates: list[dict[str, Any]] = []
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
            evidence = question.get("evidence") or []
            if isinstance(evidence, str):
                evidence = [evidence] if evidence.strip() else []
            wrong_candidates.append(
                {
                    "source_question_ref": _source_ref(question, result),
                    "test_title": str(result.get("test_title") or row.test_id),
                    "question_number": question.get("number"),
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
                    "evidence": [str(item) for item in evidence if str(item).strip()],
                    "created_at": row.created_at,
                }
            )

    type_matrix = _aggregate(
        rows, key_fields=("question_subtype", "question_type")
    )
    part_matrix = _aggregate(rows, key_fields=("source_part_number",))
    representative: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    for item in reversed(wrong_candidates):
        ref = str(item.get("source_question_ref") or "")
        if ref and ref in seen_refs:
            continue
        if ref:
            seen_refs.add(ref)
        representative.append(item)
        if len(representative) >= 5:
            break

    insights: list[str] = []
    if rows:
        insights.append(
            f"本报告基于 {len(rows)} 次已提交练习、{total_questions} 道题，"
            f"累计正确率 {_accuracy(total_correct, total_questions)}%。"
        )
    stable_types = [item for item in type_matrix if item["total"] >= MIN_PRELIMINARY_SAMPLE]
    if stable_types:
        weakest = stable_types[0]
        insights.append(
            f"当前样本中较弱题型为“{weakest['question_type']}”，"
            f"正确率 {weakest['accuracy']}%（{weakest['total']}题，{weakest['status_label']}）。"
        )
    if len(trend) >= 2:
        change = round(trend[-1]["accuracy"] - trend[0]["accuracy"], 1)
        direction = "提高" if change > 0 else "下降" if change < 0 else "持平"
        insights.append(
            f"最近一次与最早一次记录相比正确率{direction} {abs(change)} 个百分点；"
            "不同题型和题量不可直接视为同难度测验。"
        )
    slowest_correct = _slowest_unique(timed_correct_candidates, 3)
    slowest_wrong = _slowest_unique(timed_wrong_candidates, 5)
    if slowest_correct or slowest_wrong:
        longest = max(
            [*slowest_correct, *slowest_wrong],
            key=lambda item: int(item.get("elapsed_seconds") or 0),
        )
        insights.append(
            f"当前记录中用时最多的单题是 {longest['test_title']} Q{longest['question_number']}，"
            f"用时 {longest['elapsed_seconds']} 秒，"
            f"结果为{'正确' if longest['is_correct'] else '错误'}。"
        )

    return {
        "report_type": "stage",
        "engine_version": "0.5.0-deterministic",
        "generated_from": "persisted_sessions",
        "ai_calls": 0,
        "summary": {
            "session_count": len(rows),
            "first_attempt_count": sum(1 for item in trend if item["attempt_kind"] == "first"),
            "retry_count": sum(1 for item in trend if item["attempt_kind"] == "retry"),
            "correct": total_correct,
            "total_questions": total_questions,
            "accuracy": _accuracy(total_correct, total_questions),
            "total_elapsed_seconds": total_seconds,
            "date_from": rows[0].created_at if rows else None,
            "date_to": rows[-1].created_at if rows else None,
        },
        "trend": trend,
        "question_type_matrix": type_matrix,
        "part_matrix": part_matrix,
        "representative_questions": representative,
        "slowest_correct_questions": slowest_correct,
        "slowest_wrong_questions": slowest_wrong,
        "deterministic_interpretation": insights,
        "data_notes": [
            "5–9题只显示初步倾向，10题及以上才视为较稳定样本；少于5题不作能力定性。",
            "相同训练配置的第一次记录与后续重做分开标记，避免把记忆效应误当成新能力。",
            "本报告完全由已保存Session计算，未调用AI；教师应结合学生实际做题过程判断原因。",
            "单题用时从本次升级后的新提交开始记录；升级前的历史Session没有单题用时，不参与最耗时题目排名。",
        ],
    }
