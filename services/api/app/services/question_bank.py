from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from app.domain.question_types import enrich_test

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
    output = [
        {"id": "b10-test-a", "book": "剑雅10", "book_number": 10, "name": "Test A", "title": "剑雅10 Test A", "part_count": 3, "question_count": 40},
        {"id": "b10-test-b", "book": "剑雅10", "book_number": 10, "name": "Test B", "title": "剑雅10 Test B", "part_count": 3, "question_count": 40},
    ]
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


class QuestionBank:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.test_dir = self.root / "tests"
        self.index_path = self.root / "test_index.json"

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
        return data

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
