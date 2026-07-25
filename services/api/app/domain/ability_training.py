from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterable

from app.services.question_bank import ANSWER_FIELDS, QuestionBank


@dataclass(frozen=True, slots=True)
class AbilitySkill:
    id: str
    label: str
    objective: str
    subtype_ids: tuple[str, ...]
    cues: tuple[str, ...] = ()


SKILLS: tuple[AbilitySkill, ...] = (
    AbilitySkill(
        id="locating",
        label="定位",
        objective="用主体、专有名词、数字和独特细节缩小证据范围。",
        subtype_ids=(
            "matching_information",
            "matching_features",
            "matching_names",
            "matching_places",
            "true_false_not_given",
            "yes_no_not_given",
        ),
    ),
    AbilitySkill(
        id="paraphrase",
        label="同义替换",
        objective="识别词形、近义词、上下位词和句式变化。",
        subtype_ids=(
            "true_false_not_given",
            "yes_no_not_given",
            "multiple_choice_single",
            "multiple_choice_multiple",
            "matching_information",
            "matching_features",
            "matching_sentence_endings",
        ),
    ),
    AbilitySkill(
        id="main-detail",
        label="主旨与细节",
        objective="区分段落中心、作者目的、例子和局部细节。",
        subtype_ids=(
            "matching_headings",
            "multiple_choice_single",
            "matching_information",
        ),
    ),
    AbilitySkill(
        id="scope-degree",
        label="范围与程度",
        objective="核对主体、数量、频率、程度和限定条件是否完全一致。",
        subtype_ids=(
            "true_false_not_given",
            "yes_no_not_given",
            "multiple_choice_single",
            "multiple_choice_multiple",
        ),
    ),
    AbilitySkill(
        id="time-cause",
        label="时间与因果",
        objective="识别先后、条件、原因、结果和转折关系。",
        subtype_ids=(
            "true_false_not_given",
            "yes_no_not_given",
            "multiple_choice_single",
            "sentence_completion",
            "summary_completion",
            "note_completion",
            "flow_chart_completion",
        ),
        cues=("before", "after", "because", "cause", "result", "when", "during", "until"),
    ),
    AbilitySkill(
        id="answer-boundary",
        label="答案边界",
        objective="从原文截取满足语法和词数限制的最短完整答案。",
        subtype_ids=(
            "sentence_completion",
            "summary_completion",
            "note_completion",
            "table_completion",
            "flow_chart_completion",
            "diagram_label_completion",
            "short_answer",
        ),
    ),
    AbilitySkill(
        id="spelling-plural",
        label="拼写和单复数",
        objective="保留原文拼写，并根据句法判断单复数、数字和单位。",
        subtype_ids=(
            "sentence_completion",
            "summary_completion",
            "note_completion",
            "table_completion",
            "flow_chart_completion",
            "diagram_label_completion",
            "short_answer",
        ),
    ),
)

SKILL_BY_ID = {skill.id: skill for skill in SKILLS}


def skill_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": skill.id,
            "label": skill.label,
            "objective": skill.objective,
            "subtype_ids": list(skill.subtype_ids),
            "source_policy": "仅使用已迁入并通过哈希校验的真实题库",
        }
        for skill in SKILLS
    ]


def _question_count(test: dict[str, Any]) -> int:
    return sum(
        len(group.get("questions") or [])
        for part in test.get("parts") or []
        for group in part.get("groups") or []
    )


def _part_passage(part: dict[str, Any]) -> dict[str, Any]:
    return {
        "part_number": int(part.get("number") or 0),
        "title": str(part.get("title") or ""),
        "article_title": str(part.get("article_title") or ""),
        "subtitle": str(part.get("subtitle") or ""),
        "paragraphs": [
            {
                "label": str(paragraph.get("label") or ""),
                "index": paragraph.get("index"),
                "text": str(paragraph.get("text") or ""),
            }
            for paragraph in (part.get("paragraphs") or [])
            if isinstance(paragraph, dict) and str(paragraph.get("text") or "").strip()
        ],
    }


def _public_group(group: dict[str, Any], question: dict[str, Any], ref_id: str) -> dict[str, Any]:
    allowed_group = {
        "instructions": str(group.get("instructions") or ""),
        "question_type": str(group.get("question_type") or "other"),
        "question_subtype": str(group.get("question_subtype") or group.get("question_type") or "other"),
        "question_category": str(group.get("question_category") or ""),
        "question_label": str(group.get("question_label") or ""),
        "normalized_options": copy.deepcopy(group.get("normalized_options") or []),
        "required_choices": int(group.get("required_choices") or 1),
    }
    allowed_question = {
        "id": ref_id,
        "number": question.get("number"),
        "display_number": question.get("display_number"),
        "prompt": str(question.get("prompt") or ""),
        "options": copy.deepcopy(question.get("options") or []),
    }
    assert ANSWER_FIELDS.isdisjoint(allowed_group)
    assert ANSWER_FIELDS.isdisjoint(allowed_question)
    return {**allowed_group, "questions": [allowed_question]}


def _matches_skill(skill: AbilitySkill, group: dict[str, Any], question: dict[str, Any]) -> bool:
    subtype = str(group.get("question_subtype") or group.get("question_type") or "other")
    if subtype not in skill.subtype_ids:
        return False
    if not skill.cues:
        return True
    text = " ".join(
        [str(group.get("instructions") or ""), str(question.get("prompt") or "")]
    ).casefold()
    return any(cue in text for cue in skill.cues) or subtype in {
        "flow_chart_completion",
        "true_false_not_given",
        "yes_no_not_given",
    }


def iter_candidates(bank: QuestionBank, skill_id: str) -> Iterable[dict[str, Any]]:
    skill = SKILL_BY_ID.get(skill_id)
    if not skill:
        raise KeyError(skill_id)
    for index_item in bank.index():
        test_id = str(index_item["id"])
        test = bank.load_server_test(test_id)
        if _question_count(test) != 40:
            continue
        for part in test.get("parts") or []:
            part_number = int(part.get("number") or 0)
            for group_index, group in enumerate(part.get("groups") or []):
                for question_index, question in enumerate(group.get("questions") or []):
                    if not _matches_skill(skill, group, question):
                        continue
                    original_question_id = str(question.get("id") or "")
                    ref_id = f"{test_id}:{part_number}:{original_question_id}"
                    yield {
                        "ref_id": ref_id,
                        "test_id": test_id,
                        "test_title": str(test.get("title") or test_id),
                        "part_number": part_number,
                        "group_index": group_index,
                        "question_index": question_index,
                        "original_question_id": original_question_id,
                        "skill_id": skill_id,
                        "passage": _part_passage(part),
                        "group": _public_group(group, question, ref_id),
                    }


def available_counts(bank: QuestionBank) -> dict[str, int]:
    return {skill.id: sum(1 for _ in iter_candidates(bank, skill.id)) for skill in SKILLS}


def generate_ability_set(
    bank: QuestionBank,
    *,
    skill_id: str,
    count: int,
    cursor: int = 0,
) -> dict[str, Any]:
    skill = SKILL_BY_ID.get(skill_id)
    if not skill:
        raise KeyError(skill_id)
    bounded_count = max(1, min(int(count), 20))
    candidates = list(iter_candidates(bank, skill_id))
    if not candidates:
        return {
            "id": f"ability-{skill_id}-{cursor}",
            "skill": skill_catalog_item(skill),
            "items": [],
            "total_available": 0,
            "next_cursor": 0,
        }
    start = max(0, int(cursor)) % len(candidates)
    selected = [candidates[(start + offset) % len(candidates)] for offset in range(min(bounded_count, len(candidates)))]
    return {
        "id": f"ability-{skill_id}-{start}",
        "skill": skill_catalog_item(skill),
        "items": selected,
        "total_available": len(candidates),
        "next_cursor": (start + len(selected)) % len(candidates),
        "source_policy": "verified_question_bank_only",
    }


def skill_catalog_item(skill: AbilitySkill) -> dict[str, Any]:
    return {
        "id": skill.id,
        "label": skill.label,
        "objective": skill.objective,
        "subtype_ids": list(skill.subtype_ids),
    }


def _find_authoritative_question(
    bank: QuestionBank,
    ref_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    parts = ref_id.split(":", 2)
    if len(parts) != 3:
        raise ValueError(f"Invalid question reference: {ref_id}")
    test_id, part_text, original_question_id = parts
    try:
        part_number = int(part_text)
    except ValueError as error:
        raise ValueError(f"Invalid question reference: {ref_id}") from error
    test = bank.load_server_test(test_id)
    for part in test.get("parts") or []:
        if int(part.get("number") or 0) != part_number:
            continue
        for group in part.get("groups") or []:
            for question in group.get("questions") or []:
                if str(question.get("id") or "") == original_question_id:
                    return test, part, group, ref_id
    raise ValueError(f"Question reference not found: {ref_id}")


def build_authoritative_ability_test(
    bank: QuestionBank,
    *,
    skill_id: str,
    question_refs: list[str],
) -> dict[str, Any]:
    skill = SKILL_BY_ID.get(skill_id)
    if not skill:
        raise KeyError(skill_id)
    if not question_refs:
        raise ValueError("At least one question reference is required")
    if len(question_refs) > 20:
        raise ValueError("Ability training accepts at most 20 questions")
    seen: set[str] = set()
    synthetic_parts: list[dict[str, Any]] = []
    part_lookup: dict[tuple[str, int], dict[str, Any]] = {}
    for ref_id in question_refs:
        if ref_id in seen:
            raise ValueError(f"Duplicate question reference: {ref_id}")
        seen.add(ref_id)
        source_test, source_part, source_group, unique_id = _find_authoritative_question(bank, ref_id)
        subtype = str(source_group.get("question_subtype") or source_group.get("question_type") or "other")
        if subtype not in skill.subtype_ids:
            raise ValueError(f"Question {ref_id} does not belong to skill {skill_id}")
        original_question_id = ref_id.split(":", 2)[2]
        source_question = next(
            question
            for question in source_group.get("questions") or []
            if str(question.get("id") or "") == original_question_id
        )
        key = (str(source_test.get("id") or ""), int(source_part.get("number") or 0))
        synthetic_part = part_lookup.get(key)
        if synthetic_part is None:
            synthetic_part = {
                "number": len(synthetic_parts) + 1,
                "title": f"{source_test.get('title')} · Part {source_part.get('number')}",
                "source_test_id": source_test.get("id"),
                "groups": [],
            }
            part_lookup[key] = synthetic_part
            synthetic_parts.append(synthetic_part)
        synthetic_question = copy.deepcopy(source_question)
        synthetic_question["id"] = unique_id
        synthetic_question["original_question_id"] = original_question_id
        synthetic_group = {
            key_name: copy.deepcopy(value)
            for key_name, value in source_group.items()
            if key_name != "questions"
        }
        synthetic_group["questions"] = [synthetic_question]
        synthetic_part["groups"].append(synthetic_group)
    return {
        "id": f"ability-{skill_id}",
        "title": f"{skill.label}能力训练",
        "practice_mode": "ability",
        "parts": synthetic_parts,
        "source_question_refs": list(question_refs),
        "skill_id": skill_id,
    }
