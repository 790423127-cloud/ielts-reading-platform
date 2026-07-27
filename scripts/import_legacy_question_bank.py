from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

API_ROOT = Path(__file__).resolve().parents[1] / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from app.services.question_bank import QuestionBank, canonical_json_bytes, expected_test_index  # noqa: E402


def question_count(test: dict) -> int:
    return sum(
        len(group.get("questions") or [])
        for part in test.get("parts") or []
        for group in part.get("groups") or []
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the verified legacy IELTS GT Reading question bank.")
    parser.add_argument("--source", type=Path, required=True, help="Path to the legacy repository data directory")
    parser.add_argument("--destination", type=Path, default=API_ROOT / "data" / "question-bank")
    parser.add_argument("--check", action="store_true", help="Validate only; do not copy")
    args = parser.parse_args()

    source_index = args.source / "test_index.json"
    source_tests = args.source / "tests"
    if not source_index.is_file() or not source_tests.is_dir():
        raise SystemExit("Legacy data directory must contain test_index.json and tests/")

    expected = expected_test_index()
    expected_ids = [item["id"] for item in expected]
    source_meta = json.loads(source_index.read_text("utf-8"))
    source_ids = [str(item.get("id") or "") for item in source_meta]
    if source_ids != expected_ids:
        raise SystemExit("Legacy test index does not match the frozen 58-test order")

    manifest: list[dict] = []
    for item in expected:
        path = source_tests / f"{item['id']}.json"
        if not path.is_file():
            raise SystemExit(f"Missing source test: {path.name}")
        raw = canonical_json_bytes(path.read_bytes())
        test = json.loads(raw.decode("utf-8"))
        if str(test.get("id") or "") != item["id"]:
            raise SystemExit(f"ID mismatch: {path.name}")
        count = question_count(test)
        if count != 40:
            raise SystemExit(f"Expected 40 questions in {path.name}, found {count}")
        manifest.append({
            "id": item["id"],
            "path": f"data/tests/{item['id']}.json",
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "questions": count,
        })

    if not args.check:
        destination_tests = args.destination / "tests"
        destination_tests.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_index, args.destination / "test_index.json")
        for item in expected:
            source_path = source_tests / f"{item['id']}.json"
            (destination_tests / f"{item['id']}.json").write_bytes(
                canonical_json_bytes(source_path.read_bytes())
            )
        (args.destination / "migration_manifest.json").write_text(
            json.dumps(
                {"tests": manifest, "total_questions": len(expected) * 40},
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            "utf-8",
        )

    bank = QuestionBank(args.destination if not args.check else args.source)
    status = bank.migration_status()
    print(json.dumps({"ok": True, "status": status, "tests": manifest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
