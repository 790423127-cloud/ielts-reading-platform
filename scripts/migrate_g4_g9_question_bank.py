from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any


NEW_TEST_IDS = [
    f"b{book}-test-{form}"
    for book in range(4, 10)
    for form in ("a", "b")
]
EXPECTED_SOURCE_ARCHIVE_SHA256 = (
    "AA651EFBFA64F58676A8AE05B5912CC68057585E960998DE9DC56A66B41A9574"
)


def canonical_json_bytes(raw: bytes) -> bytes:
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def semantic_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def question_rows(test: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        question
        for part in test.get("parts") or []
        for group in part.get("groups") or []
        for question in group.get("questions") or []
    ]


def index_entry(test: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(test["id"]),
        "book": str(test["book"]),
        "book_number": int(test["book_number"]),
        "name": str(test["name"]),
        "title": str(test["title"]),
        "part_count": len(test.get("parts") or []),
        "question_count": len(question_rows(test)),
    }


def sort_key(item: dict[str, Any]) -> tuple[int, int]:
    name = str(item.get("name") or "")
    order = {"Test A": 1, "Test B": 2}
    if name in order:
        return int(item["book_number"]), order[name]
    return int(item["book_number"]), int(name.removeprefix("Test "))


def validate_source_report(source_data: Path) -> dict[str, Any]:
    report_path = source_data.parent / "G4_9_IMPORT_REPORT.json"
    if not report_path.is_file():
        raise RuntimeError(f"缺少旧版导入审计报告：{report_path}")
    report = load_json(report_path)
    if report.get("archive_sha256") != EXPECTED_SOURCE_ARCHIVE_SHA256:
        raise RuntimeError("旧版 G4–9 来源压缩包 SHA-256 与已审核值不一致")
    validation = report.get("validation") or {}
    expected = {
        "tests": 12,
        "parts": 36,
        "questions": 480,
        "unique_question_ids": 480,
    }
    if {key: validation.get(key) for key in expected} != expected:
        raise RuntimeError("旧版 G4–9 导入报告的题数或唯一 ID 数不符合已审核结果")
    repairs = {
        str(item.get("test_id") or "")
        for item in report.get("approved_source_repairs") or []
    }
    if repairs != {"b4-test-a", "b8-test-b"}:
        raise RuntimeError("旧版 G4–9 已批准的确定性来源修复记录不完整")
    return report


def validate_test(test_id: str, test: dict[str, Any]) -> None:
    if str(test.get("id") or "") != test_id:
        raise RuntimeError(f"{test_id} 文件内 ID 不匹配")
    if len(test.get("parts") or []) != 3:
        raise RuntimeError(f"{test_id} 不是 3 个 Part")
    questions = question_rows(test)
    if len(questions) != 40 or int(test.get("question_count") or 0) != 40:
        raise RuntimeError(f"{test_id} 不是 40 题")
    if [int(item["number"]) for item in questions] != list(range(1, 41)):
        raise RuntimeError(f"{test_id} 题号不是连续 1–40")
    if any(not str(item.get("prompt") or "").strip() for item in questions):
        raise RuntimeError(f"{test_id} 存在空题干")
    if any(not str(item.get("answer") or "").strip() for item in questions):
        raise RuntimeError(f"{test_id} 存在空标准答案")


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        newline="\n",
    ) as handle:
        handle.write(text)
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def build_plan(source_data: Path, destination: Path) -> dict[str, Any]:
    source_tests = source_data / "tests"
    destination_tests = destination / "tests"
    validate_source_report(source_data)

    source_index = load_json(source_data / "test_index.json")
    source_index_ids = [str(item.get("id") or "") for item in source_index]
    expected_source_ids = [
        *NEW_TEST_IDS,
        "b10-test-a",
        "b10-test-b",
        *[
            f"b{book}-test-{number}"
            for book in range(11, 22)
            for number in range(1, 5)
        ],
    ]
    if source_index_ids != expected_source_ids:
        raise RuntimeError("旧版 test_index.json 不是已审核的 58 套顺序")

    source_values: dict[str, dict[str, Any]] = {}
    source_bytes: dict[str, bytes] = {}
    all_question_ids: list[str] = []
    for test_id in expected_source_ids:
        path = source_tests / f"{test_id}.json"
        if not path.is_file():
            raise RuntimeError(f"旧版缺少 {path.name}")
        raw = canonical_json_bytes(path.read_bytes())
        test = json.loads(raw.decode("utf-8"))
        validate_test(test_id, test)
        source_values[test_id] = test
        source_bytes[test_id] = raw
        all_question_ids.extend(str(item["id"]) for item in question_rows(test))
    if len(all_question_ids) != len(set(all_question_ids)):
        raise RuntimeError("58 套题库存在重复 question_id")

    overlap_ids = expected_source_ids[len(NEW_TEST_IDS):]
    semantic_mismatches = []
    for test_id in overlap_ids:
        destination_path = destination_tests / f"{test_id}.json"
        if not destination_path.is_file():
            raise RuntimeError(f"新版原有题库缺少 {destination_path.name}")
        destination_value = load_json(destination_path)
        if semantic_digest(destination_value) != semantic_digest(source_values[test_id]):
            semantic_mismatches.append(test_id)
    if semantic_mismatches:
        raise RuntimeError(f"拒绝迁移：新版原有 46 套与旧版语义不一致：{semantic_mismatches}")

    existing_new_ids = [
        test_id
        for test_id in NEW_TEST_IDS
        if (destination_tests / f"{test_id}.json").exists()
    ]
    if existing_new_ids:
        raise RuntimeError(f"拒绝覆盖新版已存在文件：{existing_new_ids}")

    index = sorted(
        [index_entry(source_values[test_id]) for test_id in expected_source_ids],
        key=sort_key,
    )
    manifest_tests = []
    for item in index:
        test_id = item["id"]
        raw = source_bytes[test_id]
        manifest_tests.append(
            {
                "id": test_id,
                "path": f"data/tests/{test_id}.json",
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "questions": 40,
            }
        )
    return {
        "source_archive_sha256": EXPECTED_SOURCE_ARCHIVE_SHA256,
        "new_test_ids": NEW_TEST_IDS,
        "source_bytes": source_bytes,
        "index": index,
        "manifest": {
            "tests": manifest_tests,
            "total_questions": len(index) * 40,
        },
        "summary": {
            "tests_before": len(index) - len(NEW_TEST_IDS),
            "tests_added": len(NEW_TEST_IDS),
            "tests_after": len(index),
            "questions_added": len(NEW_TEST_IDS) * 40,
            "questions_after": len(index) * 40,
            "overlap_semantic_matches": len(overlap_ids),
        },
    }


def apply_plan(plan: dict[str, Any], destination: Path, backup_dir: Path) -> None:
    destination_tests = destination / "tests"
    backup_dir.mkdir(parents=True, exist_ok=False)
    for name in ("test_index.json", "migration_manifest.json"):
        shutil.copy2(destination / name, backup_dir / name)

    for test_id in plan["new_test_ids"]:
        (destination_tests / f"{test_id}.json").write_bytes(
            plan["source_bytes"][test_id]
        )
    write_json_atomic(destination / "test_index.json", plan["index"])
    write_json_atomic(destination / "migration_manifest.json", plan["manifest"])
    write_json_atomic(
        backup_dir / "migration-result.json",
        {
            "source_archive_sha256": plan["source_archive_sha256"],
            "added_files": [f"{test_id}.json" for test_id in plan["new_test_ids"]],
            "summary": plan["summary"],
            "rollback": {
                "restore": ["test_index.json", "migration_manifest.json"],
                "remove": [f"tests/{test_id}.json" for test_id in plan["new_test_ids"]],
            },
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and migrate the audited Cambridge G4–G9 tests into the new question bank."
    )
    parser.add_argument("--source-data", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    source_data = args.source_data.resolve()
    destination = args.destination.resolve()
    plan = build_plan(source_data, destination)
    if args.apply:
        if args.backup_dir is None:
            raise SystemExit("--apply 必须同时提供 --backup-dir")
        apply_plan(plan, destination, args.backup_dir.resolve())
    print(
        json.dumps(
            {
                "ok": True,
                "applied": args.apply,
                "summary": plan["summary"],
                "new_test_ids": plan["new_test_ids"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
