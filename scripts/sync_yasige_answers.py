from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


SOURCE_NAME = re.compile(
    r"^C(?P<book>\d+)-Test (?P<test>[A-B]|\d+)-(?:Section|Passage) (?P<part>\d+)$",
    re.IGNORECASE,
)
QUESTION_RANGE = re.compile(
    r"\bQuestions?\s*(?P<start>\d+)(?:\s*[-\u2013]\s*(?P<end>\d+))?",
    re.IGNORECASE,
)
CHOICE_COUNT = re.compile(
    r"\b(?:choose|which)\s+(?P<count>two|three|four|2|3|4)\b",
    re.IGNORECASE,
)
COUNT_WORDS = {"two": 2, "three": 3, "four": 4}
NUMBER_WORDS = {
    str(number): word
    for number, word in enumerate(
        (
            "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
            "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
            "eighteen", "nineteen",
        )
    )
}
JUDGEMENT_ALIASES = {
    "TRUE": "T",
    "FALSE": "F",
    "NOT GIVEN": "NG",
    "YES": "Y",
    "NO": "N",
}


def plain_text(value: Any) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).strip()


def displayed_question_range(value: Any) -> tuple[int, int] | None:
    match = QUESTION_RANGE.search(plain_text(value))
    if not match:
        return None
    start = int(match.group("start"))
    return start, int(match.group("end") or start)


def source_reference(source_name: str) -> tuple[str, int] | None:
    match = SOURCE_NAME.match(source_name.strip())
    if not match:
        return None
    book = int(match.group("book"))
    raw_test = match.group("test").lower()
    if raw_test.isdigit():
        test_number = int(raw_test)
        if book == 12 and 5 <= test_number <= 8:
            test_number -= 4
        test_id = f"b{book}-test-{test_number}"
    else:
        test_id = f"b{book}-test-{raw_test}"
    return test_id, int(match.group("part"))


def load_latest_parts(cache_root: Path) -> dict[tuple[str, int], dict[str, Any]]:
    parts: dict[tuple[str, int], dict[str, Any]] = {}
    for cache_file in sorted(cache_root.iterdir(), key=lambda path: path.stat().st_mtime_ns):
        if not cache_file.is_file():
            continue
        try:
            payload = json.loads(cache_file.read_text("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, OSError):
            continue
        content = payload.get("content") if isinstance(payload, dict) else None
        for item in content if isinstance(content, list) else []:
            if not isinstance(item, dict):
                continue
            reference = source_reference(str(item.get("passagesQuestion") or ""))
            if reference is None or not 5 <= int(reference[0].split("-", 1)[0][1:]) <= 20:
                continue
            parts[reference] = item
    return parts


def parse_answer_json(group: dict[str, Any]) -> list[dict[str, Any]]:
    raw = group.get("answerJson")
    if isinstance(raw, str):
        loaded = json.loads(raw)
    else:
        loaded = raw or []
    return [item for item in loaded if isinstance(item, dict)]


def option_codes(group: dict[str, Any], answer_index: int) -> list[str]:
    question_json = group.get("questionJson") or {}
    source_questions = question_json.get("questions") or []
    source_question = source_questions[min(answer_index, max(0, len(source_questions) - 1))] if source_questions else {}
    return [
        chr(65 + index)
        for index, option in enumerate(source_question.get("options") or [])
        if isinstance(option, dict)
    ]


def source_answer(
    group: dict[str, Any],
    answer: dict[str, Any],
    answer_index: int,
) -> tuple[str, list[str], int | None]:
    question_type = int(group.get("questionType") or 0)
    question_json = group.get("questionJson") or {}
    correct = answer.get("correctValue")
    if question_type == 0:
        raw = plain_text(correct)
        accepted = [item.strip() for item in raw.split("/") if item.strip()]
        if not accepted:
            accepted = [raw] if raw else []
        code_tokens = re.findall(r"\b[A-Z]\b", accepted[0]) if accepted else []
        required = len(dict.fromkeys(code_tokens)) if len(code_tokens) > 1 else None
        return (accepted[0] if accepted else raw), accepted, required

    if question_type == 4:
        match_options = question_json.get("matchOptions") or []
        code = str(match_options[int(correct)].get("index") or "")
        return code, [code], None

    codes = option_codes(group, answer_index)
    if question_type == 2:
        selected = [codes[int(index)] for index in (correct or [])]
        canonical = ",".join(selected)
        return canonical, [canonical], len(selected)

    if question_type == 3:
        source_questions = question_json.get("questions") or []
        source_question = source_questions[min(answer_index, max(0, len(source_questions) - 1))] if source_questions else {}
        options = source_question.get("options") or []
        text = plain_text(options[int(correct)].get("content") if options else "").upper()
        code = text or codes[int(correct)]
        aliases = {
            "TRUE": "T",
            "FALSE": "F",
            "NOT GIVEN": "NG",
            "YES": "Y",
            "NO": "N",
        }
        accepted = [code]
        if code in aliases:
            accepted.append(aliases[code])
        return code, accepted, None

    code = codes[int(correct)]
    return code, [code], None


def required_choice_count(group: dict[str, Any]) -> int | None:
    descriptions = plain_text((group.get("questionJson") or {}).get("descriptions"))
    match = CHOICE_COUNT.search(descriptions)
    if not match:
        return None
    token = match.group("count").lower()
    return COUNT_WORDS.get(token, int(token) if token.isdigit() else None)


def question_map(part: dict[str, Any]) -> dict[int, tuple[dict[str, Any], dict[str, Any]]]:
    output: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    for group in part.get("groups") or []:
        for question in group.get("questions") or []:
            output[int(question.get("number") or 0)] = (group, question)
    return output


def sync_part(
    part: dict[str, Any],
    source_part: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], set[int]]:
    by_number = question_map(part)
    changes: list[dict[str, Any]] = []
    errors: list[str] = []
    mapped_numbers: set[int] = set()
    group_sources: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for source_group in source_part.get("questions") or []:
        question_json = source_group.get("questionJson") or {}
        answer_rows = parse_answer_json(source_group)
        question_type = int(source_group.get("questionType") or 0)
        description_range = displayed_question_range(question_json.get("descriptions"))
        navigation_range = displayed_question_range(source_group.get("questionNavigation"))
        index_range = (
            int(question_json.get("startIndex") or 0),
            int(question_json.get("endIndex") or question_json.get("startIndex") or 0),
        )
        if question_type == 2 and description_range is not None:
            display_range = description_range
        else:
            candidates = [candidate for candidate in (navigation_range, description_range, index_range) if candidate]
            display_range = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate[1] - candidate[0] + 1 == len(answer_rows)
                ),
                candidates[0],
            )
        start, end = display_range
        numbers = list(range(start, end + 1))

        if len(answer_rows) == len(numbers):
            targets = [[number] for number in numbers]
        elif question_type == 2 and len(answer_rows) == 1:
            correct = answer_rows[0].get("correctValue") or []
            shared = len(numbers) > 1 and len(correct) == len(numbers)
            targets = [numbers if shared else [numbers[0]]]
        else:
            errors.append(
                f"range {start}-{end}: {len(answer_rows)} source answers cannot map to {len(numbers)} questions"
            )
            continue

        choice_count = required_choice_count(source_group)
        for answer_index, (answer_row, target_numbers) in enumerate(zip(answer_rows, targets, strict=True)):
            answer, accepted, per_question_required = source_answer(source_group, answer_row, answer_index)
            for number in target_numbers:
                target = by_number.get(number)
                if target is None:
                    errors.append(f"missing local question {number}")
                    continue
                mapped_numbers.add(number)
                local_group, question = target
                before = {
                    "answer": question.get("answer"),
                    "accepted_answers": question.get("accepted_answers"),
                    "required_choices": question.get("required_choices"),
                }
                question["answer"] = answer
                question["accepted_answers"] = accepted
                if per_question_required:
                    question["required_choices"] = per_question_required
                else:
                    question.pop("required_choices", None)
                after = {
                    "answer": question.get("answer"),
                    "accepted_answers": question.get("accepted_answers"),
                    "required_choices": question.get("required_choices"),
                }
                if before != after:
                    changes.append({"number": number, "before": before, "after": after})
                group_sources[id(local_group)].append(source_group)
                if question_type == 2 and choice_count:
                    local_group["required_choices"] = choice_count

        if question_type == 2 and len(answer_rows) == 1 and len(targets[0]) > 1:
            target = by_number.get(targets[0][0])
            if target:
                target[0]["shared_response"] = True
                target[0]["shared_response_numbers"] = targets[0]
                target[0]["shared_response_question_ids"] = [
                    str(by_number[number][1].get("id")) for number in targets[0] if number in by_number
                ]

    return changes, errors, mapped_numbers


def canonical_json_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def refresh_question_bank_manifest(bank_root: Path) -> int:
    manifest_path = bank_root / "migration_manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    changed = 0
    for item in manifest.get("tests") or []:
        test_path = bank_root / "tests" / f"{item['id']}.json"
        if not test_path.is_file():
            continue
        raw = canonical_json_bytes(test_path)
        next_bytes = len(raw)
        next_sha = hashlib.sha256(raw).hexdigest()
        if item.get("bytes") != next_bytes or item.get("sha256") != next_sha:
            item["bytes"] = next_bytes
            item["sha256"] = next_sha
            changed += 1
    if changed:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return changed


def canonical_answer(question: dict[str, Any]) -> Any:
    accepted = [item for item in question.get("accepted_answers") or [] if str(item).strip()]
    answer = question.get("answer")
    if answer is not None and str(answer).strip():
        return answer
    return accepted[0] if accepted else ""


def alternate_answer(question: dict[str, Any], subtype: str) -> Any:
    accepted = [item for item in question.get("accepted_answers") or [] if str(item).strip()]
    if len(accepted) > 1:
        return accepted[-1]
    answer = canonical_answer(question)
    text = str(answer).strip()
    upper = text.upper()
    if upper in JUDGEMENT_ALIASES:
        return JUDGEMENT_ALIASES[upper]
    if subtype == "multiple_choice_multiple":
        parts = [part.strip() for part in re.split(r"\|\||[,|/]", text) if part.strip()]
        if len(parts) > 1:
            return list(reversed(parts))
    return NUMBER_WORDS.get(text, answer)


def regression_answers(test: dict[str, Any], scenario: str) -> dict[str, Any]:
    answers: dict[str, Any] = {}
    position = 0
    for part in test.get("parts") or []:
        for group in part.get("groups") or []:
            subtype = str(group.get("question_type") or group.get("subtype") or "other")
            for question in group.get("questions") or []:
                if scenario == "official":
                    value = canonical_answer(question)
                elif scenario == "blank":
                    value = ""
                else:
                    branch = position % 4
                    if branch == 0:
                        value = canonical_answer(question)
                    elif branch in {1, 2}:
                        value = alternate_answer(question, subtype)
                    else:
                        value = "__definitely_wrong__"
                answers[str(question["id"])] = value
                position += 1
    return answers


def regression_scenario(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "score": result["score"],
        "total": result["total"],
        "estimated_band": result.get("estimated_gt_reading_band"),
        "part_scores": [
            {
                "part_number": row["part_number"],
                "score": row["score"],
                "total": row["total"],
            }
            for row in result["part_results"]
        ],
        "question_results": [
            {
                "id": row["id"],
                "is_correct": row["is_correct"],
                "answer_error_type": row.get("answer_error_type"),
            }
            for row in result["question_results"]
        ],
    }


def refresh_scoring_references(repository_root: Path, bank_root: Path) -> int:
    api_root = repository_root / "services" / "api"
    sys.path.insert(0, str(api_root))
    from app.domain.scoring import score_submission
    from app.services.question_bank import QuestionBank

    bank = QuestionBank(bank_root)
    changed = 0
    reference_paths = (
        api_root / "tests" / "fixtures" / "g4_g9_legacy_scoring_reference.json",
        api_root / "tests" / "fixtures" / "legacy_scoring_reference.json",
    )
    for reference_path in reference_paths:
        reference = json.loads(reference_path.read_text("utf-8"))
        file_changed = False
        for test_item in reference.get("tests") or []:
            test_id = str(test_item.get("id") or "")
            match = re.match(r"b(\d+)-", test_id)
            if not match or not 5 <= int(match.group(1)) <= 20:
                continue
            test = bank.load_server_test(test_id)
            scenarios = {}
            for scenario_name in reference.get("scenario_names") or []:
                result = score_submission(
                    test,
                    regression_answers(test, str(scenario_name)),
                    exam_mode="mock_exam",
                    total_elapsed_seconds=0,
                )
                scenarios[str(scenario_name)] = regression_scenario(result)
            if test_item.get("scenarios") != scenarios:
                test_item["scenarios"] = scenarios
                file_changed = True
                changed += 1
        if file_changed:
            reference_path.write_text(
                json.dumps(reference, ensure_ascii=False, separators=(",", ":")) + "\n",
                "utf-8",
            )
    return changed


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    default_cache = Path(os.environ.get("APPDATA", "")) / "雅思哥机考软件" / "Cache" / "Cache_Data"
    parser = argparse.ArgumentParser(description="Synchronise C5-C20 IELTSBro answer keys into the local question bank.")
    parser.add_argument("--cache-root", type=Path, default=default_cache)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    source_parts = load_latest_parts(args.cache_root)
    changes: list[dict[str, Any]] = []
    errors: list[str] = []
    changed_files = 0
    manifest_rows_refreshed = 0
    scoring_references_refreshed = 0
    mapped_questions: set[tuple[str, int, int]] = set()
    test_dir = repository_root / "services" / "api" / "data" / "question-bank" / "tests"

    for test_id in sorted({test_id for test_id, _ in source_parts}):
        path = test_dir / f"{test_id}.json"
        if not path.is_file():
            errors.append(f"missing local test file: {path.name}")
            continue
        test = json.loads(path.read_text("utf-8"))
        file_changed = False
        for part in test.get("parts") or []:
            part_number = int(part.get("number") or 0)
            source_part = source_parts.get((test_id, part_number))
            if source_part is None:
                errors.append(f"missing source part: {test_id} Part {part_number}")
                continue
            part_changes, part_errors, part_mapped_numbers = sync_part(part, source_part)
            for change in part_changes:
                change.update({"test_id": test_id, "part": part_number})
                changes.append(change)
            errors.extend(f"{test_id} Part {part_number}: {message}" for message in part_errors)
            file_changed = file_changed or bool(part_changes)
            mapped_questions.update(
                (test_id, part_number, number) for number in part_mapped_numbers
            )
        if args.apply and file_changed:
            path.write_text(json.dumps(test, ensure_ascii=False, indent=2) + "\n", "utf-8")
            changed_files += 1

    if args.apply and not errors:
        bank_root = test_dir.parent
        manifest_rows_refreshed = refresh_question_bank_manifest(bank_root)
        scoring_references_refreshed = refresh_scoring_references(repository_root, bank_root)

    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "source_parts": len(source_parts),
        "source_tests": len({test_id for test_id, _ in source_parts}),
        "mapped_answered_questions": len(mapped_questions),
        "changed_answer_rows": len(changes),
        "changed_files": changed_files,
        "manifest_rows_refreshed": manifest_rows_refreshed,
        "scoring_references_refreshed": scoring_references_refreshed,
        "errors": errors,
        "sample_changes": changes[:20],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
