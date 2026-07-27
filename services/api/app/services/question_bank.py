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
        self._difficulty_cache: tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]] | None = None

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

    @staticmethod
    def _repair_question_copy(test: dict[str, Any]) -> None:
        """Repair a verified legacy OCR confusion without changing frozen source files."""

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
        found = [item["id"] for item in expected if (self.test_dir / f"{item['id']}.json").is_file()]
        return {
            "expected_tests": len(expected),
            "found_tests": len(found),
            "expected_questions": len(expected) * 40,
            "ready": len(found) == len(expected),
            "missing_test_ids": [item["id"] for item in expected if item["id"] not in found],
        }

    def require_ready(self) -> None:
        status = self.migration_status()
        if not status["ready"]:
            raise QuestionBankNotReadyError(
                f"Question bank migration incomplete: {status['found_tests']}/{status['expected_tests']} tests"
            )

    def index(self) -> list[dict[str, Any]]:
        self.require_ready()
        if self.index_path.is_file():
            data = json.loads(self.index_path.read_text("utf-8"))
        else:
            data = expected_test_index()
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
        return enrich_test(test)

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
