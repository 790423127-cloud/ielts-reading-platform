from __future__ import annotations

import copy
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from app.domain.ability_training import generate_ability_set
from app.domain.difficulty_ratings import build_difficulty_catalog
from app.main import create_app
from app.repositories.session_repository import SQLiteSessionRepository
from app.services.question_bank import QuestionBank


@pytest.fixture
def question_bank() -> QuestionBank:
    return QuestionBank(Path(__file__).resolve().parents[1] / "data" / "question-bank")


def test_difficulty_is_relative_and_answer_independent(question_bank) -> None:
    tests = [
        question_bank.load_server_test(item["id"])
        for item in question_bank.index()
    ]
    baseline, parts = build_difficulty_catalog(tests)
    mutated = copy.deepcopy(tests)
    for test in mutated:
        for part in test["parts"]:
            for group in part["groups"]:
                for question in group["questions"]:
                    question["answer"] = "must-not-change-difficulty"
    changed, changed_parts = build_difficulty_catalog(mutated)
    assert changed == baseline
    assert changed_parts == parts
    assert {row["level"] for row in baseline.values()} == {"easy", "medium", "hard"}
    assert all(row["official"] is False for row in baseline.values())


def test_wrong_batch_accepts_verified_mixed_subtypes(question_bank) -> None:
    refs = []
    for test_id in ("b21-test-1", "b20-test-1", "b19-test-1"):
        test = question_bank.load_server_test(test_id)
        seen = set()
        for part in test["parts"]:
            for group in part["groups"]:
                subtype = group["question_subtype"]
                if subtype in seen or not group["questions"]:
                    continue
                seen.add(subtype)
                question = group["questions"][0]
                refs.append(f"{test_id}:{part['number']}:{question['id']}")
                if len({row.split(":", 2)[0] for row in refs}) >= 2 and len(refs) >= 4:
                    break
            if len(refs) >= 4:
                break
        if len(refs) >= 4:
            break
    generated = generate_ability_set(
        question_bank, skill_id="wrong-batch", count=len(refs), question_refs=refs
    )
    assert generated["training_kind"] == "wrong_batch"
    assert [row["ref_id"] for row in generated["items"]] == refs


def test_history_archive_and_teacher_snapshot_use_isolated_database(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "isolated.sqlite3"
    monkeypatch.setenv("SESSION_DB_PATH", str(database_path))
    sessions = SQLiteSessionRepository(database_path)
    stored = sessions.save_or_get(
        user_id="owner",
        client_submission_id="system-migration-test-session",
        test_id="b21-test-1",
        result={
            "test_id": "b21-test-1",
            "test_title": "Test",
            "score": 1,
            "total": 1,
            "accuracy": 100,
            "part_numbers": [1],
            "part_results": [],
            "question_results": [],
            "wrong_questions": [],
            "total_elapsed_seconds": 30,
        },
    )
    client = TestClient(create_app())
    assignment = client.post(
        "/api/v1/teacher/assignments",
        json={"user_id": "owner", "title": "Teacher migration test"},
    ).json()
    updated = client.put(
        f"/api/v1/teacher/assignments/{assignment['id']}",
        json={
            "user_id": "owner",
            "title": assignment["title"],
            "description": "",
            "status": "active",
            "session_ids": [stored.id],
            "modules": [
                {
                    "id": "module-full-test",
                    "title": "完整套题模块",
                    "module_type": "full_test",
                    "target_count": 1,
                    "session_ids": [stored.id],
                },
                {
                    "id": "module-review",
                    "title": "错题复习模块",
                    "module_type": "review",
                    "target_count": 3,
                    "session_ids": [],
                },
            ],
        },
    )
    assert updated.status_code == 200
    assert [row["title"] for row in updated.json()["modules"]] == [
        "完整套题模块",
        "错题复习模块",
    ]
    assert updated.json()["session_ids"] == [stored.id]
    snapshot = client.post(
        f"/api/v1/teacher/assignments/{assignment['id']}/snapshots?user_id=owner"
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["report"]["summary"]["session_count"] == 1
    assert snapshot.json()["report"]["ai_calls"] == 0

    pdf = client.get(
        f"/api/v1/teacher/assignments/{assignment['id']}/report.pdf?user_id=owner"
    )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")

    docx = client.get(
        f"/api/v1/teacher/report-snapshots/{snapshot.json()['id']}.docx?user_id=owner"
    )
    assert docx.status_code == 200
    assert docx.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )
    with ZipFile(BytesIO(docx.content)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "Teacher migration test" in document_xml
    assert "标准答案、判分和 Band 规则没有改变" in document_xml

    assert client.delete(f"/api/v1/sessions/{stored.id}?user_id=owner").status_code == 200
    rows = client.get(
        "/api/v1/sessions?user_id=owner&include_archived=true"
    ).json()
    assert rows[0]["archived"] is True
    assert client.post(
        f"/api/v1/sessions/{stored.id}/restore?user_id=owner"
    ).status_code == 200
