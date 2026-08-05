from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.session_repository import SQLiteSessionRepository


def _result(title: str, score: int) -> dict:
    return {
        "test_id": title.lower().replace(" ", "-"),
        "test_title": title,
        "practice_mode": "full_test",
        "part_numbers": [1, 2, 3],
        "score": score,
        "total": 40,
        "accuracy": score / 40 * 100,
        "total_elapsed_seconds": 3600,
        "question_results": [],
        "wrong_questions": [],
        "part_results": [],
    }


def test_selected_report_uses_only_owned_selected_sessions(monkeypatch, tmp_path) -> None:
    database = tmp_path / "selected-reports.sqlite3"
    monkeypatch.setenv("SESSION_DB_PATH", str(database))
    repository = SQLiteSessionRepository(database)
    first = repository.save_or_get(
        user_id="owner",
        client_submission_id="selected-first",
        test_id="b5-test-a",
        result=_result("剑雅5 Test A", 22),
    )
    second = repository.save_or_get(
        user_id="owner",
        client_submission_id="selected-second",
        test_id="b6-test-b",
        result=_result("剑雅6 Test B", 30),
    )
    other = repository.save_or_get(
        user_id="another-user",
        client_submission_id="selected-other",
        test_id="b7-test-a",
        result=_result("剑雅7 Test A", 40),
    )
    client = TestClient(create_app())
    request = {
        "user_id": "owner",
        "session_ids": [second.id, first.id, second.id],
        "title": "最近两次练习汇总",
    }

    report = client.post("/api/v1/reports/selection", json=request)
    assert report.status_code == 200
    payload = report.json()
    assert payload["summary"]["title"] == "最近两次练习汇总"
    assert payload["summary"]["session_count"] == 2
    assert payload["summary"]["correct"] == 52
    assert payload["summary"]["total_questions"] == 80
    assert payload["summary"]["accuracy"] == 65.0
    assert set(payload["selected_session_ids"]) == {first.id, second.id}
    assert other.id not in payload["selected_session_ids"]

    pdf = client.post("/api/v1/reports/selection.pdf", json=request)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")

    docx = client.post("/api/v1/reports/selection.docx", json=request)
    assert docx.status_code == 200
    with ZipFile(BytesIO(docx.content)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "最近两次练习汇总" in document_xml
    assert "本报告仅包含用户明确勾选的 2 条练习记录" in document_xml

    inaccessible = client.post(
        "/api/v1/reports/selection",
        json={**request, "session_ids": [first.id, other.id]},
    )
    assert inaccessible.status_code == 404
    assert inaccessible.json()["detail"]["missing_session_ids"] == [other.id]

    assert len(repository.list_recent(user_id="owner", limit=10)) == 2
