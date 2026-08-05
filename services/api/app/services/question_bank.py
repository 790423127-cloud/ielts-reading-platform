from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from app.domain.question_types import enrich_test
from app.domain.difficulty_ratings import build_difficulty_catalog

ANSWER_FIELDS = {
    "answer",
    "accepted_answers",
    "analysis",
    "reason",
    "location_analysis",
    "evidence",
    "paraphrasing",
    "keywords",
    "wrong_reasons",
}

SOURCE_INTERACTION_MODES = {
    0: "text_entry",
    1: "single_choice",
    2: "multiple_choice",
    3: "judgement",
    4: "matching_matrix",
}


def expected_test_index() -> list[dict[str, Any]]:
    output = []
    for book_number in range(4, 11):
        for form in ("a", "b"):
            name = f"Test {form.upper()}"
            output.append({
                "id": f"b{book_number}-test-{form}",
                "book": f"剑雅{book_number}",
                "book_number": book_number,
                "name": name,
                "title": f"剑雅{book_number} {name}",
                "part_count": 3,
                "question_count": 40,
            })
    for book_number in range(11, 22):
        for test_number in range(1, 5):
            output.append({
                "id": f"b{book_number}-test-{test_number}",
                "book": f"剑雅{book_number}",
                "book_number": book_number,
                "name": f"Test {test_number}",
                "title": f"剑雅{book_number} Test {test_number}",
                "part_count": 3,
                "question_count": 40,
            })
    return output


def baseline_test_ids() -> set[str]:
    """Tests already present in the reproducible repository baseline."""

    return {
        item["id"]
        for item in expected_test_index()
        if int(item["book_number"]) >= 10
    }


class QuestionBankNotReadyError(RuntimeError):
    pass


def canonical_json_bytes(raw: bytes) -> bytes:
    """Normalize checkout-only UTF-8 BOM and line-ending differences."""

    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


class QuestionBank:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.test_dir = self.root / "tests"
        self.index_path = self.root / "test_index.json"
        self.layout_repairs_path = self.root / "passage_layout_repairs.json"
        self.source_html_path = self.root / "passage_source_html.local.json"
        self._source_html_cache: dict[tuple[str, int], dict[str, Any]] | None = None
        self._difficulty_cache: tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]] | None = None

    def _declared_index(self) -> list[dict[str, Any]]:
        expected = expected_test_index()
        expected_by_id = {str(item["id"]): item for item in expected}
        if not self.index_path.is_file():
            return expected
        loaded = json.loads(self.index_path.read_text("utf-8"))
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in loaded if isinstance(loaded, list) else []:
            test_id = str(item.get("id") or "")
            if test_id not in expected_by_id or test_id in seen:
                continue
            rows.append({**expected_by_id[test_id], **item})
            seen.add(test_id)
        rows.extend(item for item in expected if str(item["id"]) not in seen)
        return rows

    def _available_index(self) -> list[dict[str, Any]]:
        return [
            item
            for item in self._declared_index()
            if (self.test_dir / f"{item['id']}.json").is_file()
        ]

    def _restore_passage_layouts(self, test: dict[str, Any]) -> None:
        if not self.layout_repairs_path.is_file():
            return
        payload = json.loads(self.layout_repairs_path.read_text("utf-8"))
        repairs = [
            item
            for item in payload.get("repairs") or []
            if str(item.get("test_id") or "") == str(test.get("id") or "")
        ]
        for repair in repairs:
            part = next(
                (
                    item
                    for item in test.get("parts") or []
                    if int(item.get("number") or 0) == int(repair.get("part_number") or 0)
                ),
                None,
            )
            if not part:
                continue
            paragraph = next(
                (
                    item
                    for item in part.get("paragraphs") or []
                    if int(item.get("index") or 0) == int(repair.get("paragraph_index") or 0)
                ),
                None,
            )
            if paragraph is not None and repair.get("table"):
                paragraph["table"] = copy.deepcopy(repair["table"])

    def _source_html_by_part(self) -> dict[tuple[str, int], dict[str, Any]]:
        if self._source_html_cache is not None:
            return self._source_html_cache
        self._source_html_cache = {}
        if not self.source_html_path.is_file():
            return self._source_html_cache
        payload = json.loads(self.source_html_path.read_text("utf-8"))
        for item in payload.get("parts") or []:
            test_id = str(item.get("test_id") or "")
            part_number = int(item.get("part_number") or 0)
            if test_id and part_number > 0:
                self._source_html_cache[(test_id, part_number)] = item
        return self._source_html_cache

    def _restore_source_html(self, test: dict[str, Any]) -> None:
        source_parts = self._source_html_by_part()
        test_id = str(test.get("id") or "")
        for part in test.get("parts") or []:
            part_number = int(part.get("number") or 0)
            source_part = source_parts.get((test_id, part_number))
            if not source_part:
                continue
            passage_html = str(source_part.get("passage_html") or "").strip()
            if passage_html:
                part["source_html"] = passage_html
                part["source_visual_name"] = str(source_part.get("source_name") or "")
            groups = part.get("groups") or []
            source_groups = source_part.get("question_groups") or []
            for position, group in enumerate(groups):
                question_numbers = {
                    int(question.get("number"))
                    for question in group.get("questions") or []
                    if str(question.get("number") or "").isdigit()
                }
                matched_source_groups = []
                for source_group in source_groups:
                    display_start = int(source_group.get("display_start") or 0)
                    display_end = int(source_group.get("display_end") or display_start)
                    source_question_numbers = (
                        set(range(display_start, display_end + 1))
                        if display_start > 0 and display_end >= display_start
                        else set()
                    )
                    if source_question_numbers and source_question_numbers.issubset(question_numbers):
                        matched_source_groups.append(source_group)
                if not matched_source_groups and position < len(source_groups):
                    matched_source_groups = [source_groups[position]]
                if matched_source_groups:
                    restored_source_groups = copy.deepcopy(matched_source_groups)
                    if len(restored_source_groups) == 1:
                        restored_source_group = restored_source_groups[0]
                        display_start = int(restored_source_group.get("display_start") or 0)
                        display_end = int(restored_source_group.get("display_end") or display_start)
                        index_start = int(restored_source_group.get("start_index") or 0)
                        index_end = int(restored_source_group.get("end_index") or index_start)
                        display_matches = {
                            number
                            for number in question_numbers
                            if display_start > 0 and display_start <= number <= display_end
                        }
                        index_matches = {
                            number
                            for number in question_numbers
                            if index_start > 0 and index_start <= number <= index_end
                        }
                        if len(index_matches) > len(display_matches):
                            restored_source_group["display_start"] = min(index_matches)
                            restored_source_group["display_end"] = max(index_matches)
                    for restored_source_group in restored_source_groups:
                        try:
                            source_question_type = int(restored_source_group.get("question_type"))
                        except (TypeError, ValueError):
                            source_question_type = 0
                        restored_source_group["interaction_mode"] = SOURCE_INTERACTION_MODES.get(
                            source_question_type,
                            "text_entry",
                        )
                    group["source_question_groups"] = restored_source_groups

    @staticmethod
    def _repair_question_copy(test: dict[str, Any]) -> None:
        """Repair the verified leading lowercase-l OCR error in question copy."""

        def repair(value: Any) -> Any:
            if not isinstance(value, str):
                return value
            return f"It{value[2:]}" if value.startswith("lt ") else value

        for part in test.get("parts") or []:
            for group in part.get("groups") or []:
                for question in group.get("questions") or []:
                    question["prompt"] = repair(question.get("prompt"))
                    for option in question.get("options") or []:
                        if isinstance(option, dict):
                            for field in ("label", "text", "content"):
                                if field in option:
                                    option[field] = repair(option[field])

    def migration_status(self) -> dict[str, Any]:
        expected = expected_test_index()
        available = self._available_index()
        found_ids = {str(item["id"]) for item in available}
        missing = [str(item["id"]) for item in expected if str(item["id"]) not in found_ids]
        baseline = baseline_test_ids()
        missing_baseline = sorted(baseline - found_ids)
        return {
            "expected_tests": len(expected),
            "found_tests": len(available),
            "expected_questions": len(expected) * 40,
            "found_questions": sum(int(item.get("question_count") or 0) for item in available),
            "ready": not missing,
            "baseline_expected_tests": len(baseline),
            "baseline_ready": not missing_baseline,
            "missing_test_ids": missing,
            "missing_baseline_test_ids": missing_baseline,
        }

    def require_ready(self) -> None:
        status = self.migration_status()
        if not status["baseline_ready"]:
            raise QuestionBankNotReadyError(
                "Question bank baseline incomplete: "
                f"{status['found_tests']}/{status['baseline_expected_tests']} available; "
                f"missing baseline tests: {', '.join(status['missing_baseline_test_ids'][:5])}"
            )

    def index(self) -> list[dict[str, Any]]:
        self.require_ready()
        data = self._available_index()
        if self._difficulty_cache is None:
            tests = [self.load_server_test(str(item["id"])) for item in data]
            self._difficulty_cache = build_difficulty_catalog(tests)
        test_ratings, part_ratings = self._difficulty_cache
        return [
            {
                **item,
                "difficulty": test_ratings.get(str(item["id"]), {}),
                "part_difficulties": part_ratings.get(str(item["id"]), []),
            }
            for item in data
        ]

    def load_server_test(self, test_id: str) -> dict[str, Any]:
        allowed = {item["id"] for item in expected_test_index()}
        if test_id not in allowed:
            raise KeyError(test_id)
        path = self.test_dir / f"{test_id}.json"
        if not path.is_file():
            raise QuestionBankNotReadyError(f"Missing migrated test: {test_id}")
        test = json.loads(path.read_text("utf-8"))
        if str(test.get("id") or "") != test_id:
            raise ValueError(f"Question bank id mismatch in {path.name}")
        self._restore_passage_layouts(test)
        self._repair_question_copy(test)
        test = enrich_test(test)
        self._restore_source_html(test)
        return test

    def load_public_test(self, test_id: str) -> dict[str, Any]:
        test = copy.deepcopy(self.load_server_test(test_id))
        for part in test.get("parts") or []:
            for group in part.get("groups") or []:
                for field in ANSWER_FIELDS:
                    group.pop(field, None)
                for question in group.get("questions") or []:
                    for field in ANSWER_FIELDS:
                        question.pop(field, None)
        return test


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
