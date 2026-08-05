from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _annotation(*, part_number: int = 1, kind: str = "note") -> dict[str, object]:
    return {
        "id": "annotation-0001",
        "kind": kind,
        "testId": "b10-test-a",
        "testTitle": "客户端标题不会覆盖服务端标题",
        "partNumber": part_number,
        "paragraphIndex": 0,
        "startOffset": 4,
        "endOffset": 15,
        "selectedText": "substantial",
        "prefix": "A",
        "suffix": "proportion",
        "sentence": "A substantial proportion supported the plan.",
        "note": "表示数量很大" if kind == "note" else "",
        "createdAt": "2026-07-26T00:00:00+00:00",
        "updatedAt": "2026-07-26T00:00:00+00:00",
    }


def test_secondary_highlight_level_is_accepted_and_preserved(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SESSION_DB_PATH", str(tmp_path / "secondary-highlight.sqlite3"))
    client = TestClient(app)
    annotation = _annotation(kind="highlight")
    annotation["highlightLevel"] = "secondary"
    response = client.post(
        "/api/v1/sessions/submit",
        json={
            "test_id": "b10-test-a",
            "client_submission_id": "secondary-highlight-0001",
            "exam_mode": "part_practice",
            "part_numbers": [1],
            "annotations": [annotation],
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["annotations"][0]["highlightLevel"] == "secondary"


def test_annotations_are_persisted_inside_session_result(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SESSION_DB_PATH", str(tmp_path / "annotations.sqlite3"))
    client = TestClient(app)
    response = client.post(
        "/api/v1/sessions/submit",
        json={
            "user_id": "owner",
            "test_id": "b10-test-a",
            "client_submission_id": "annotations-submit-0001",
            "answers": {},
            "elapsed_seconds": 12,
            "exam_mode": "part_practice",
            "part_numbers": [1],
            "annotations": [_annotation()],
        },
    )
    assert response.status_code == 200
    envelope = response.json()
    annotation = envelope["result"]["annotations"][0]
    assert annotation["id"] == "annotation-0001"
    assert annotation["testId"] == "b10-test-a"
    assert annotation["testTitle"] == "剑雅10 Test A"
    assert annotation["partNumber"] == 1
    assert annotation["note"] == "表示数量很大"

    restored = client.get(f"/api/v1/sessions/{envelope['session_id']}?user_id=owner")
    assert restored.status_code == 200
    assert restored.json()["result"]["annotations"] == envelope["result"]["annotations"]


def test_annotation_from_another_test_or_part_is_ignored_without_blocking_score(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("SESSION_DB_PATH", str(tmp_path / "invalid-annotations.sqlite3"))
    client = TestClient(app)

    wrong_part = client.post(
        "/api/v1/sessions/submit",
        json={
            "test_id": "b10-test-a",
            "client_submission_id": "annotations-invalid-part",
            "exam_mode": "part_practice",
            "part_numbers": [1],
            "annotations": [_annotation(part_number=2)],
        },
    )
    assert wrong_part.status_code == 200
    assert wrong_part.json()["result"]["annotations"] == []
    assert wrong_part.json()["result"]["annotation_warnings"][0]["code"] == "annotation_part_not_submitted_ignored"

    wrong_test = _annotation()
    wrong_test["testId"] = "b10-test-b"
    mismatch = client.post(
        "/api/v1/sessions/submit",
        json={
            "test_id": "b10-test-a",
            "client_submission_id": "annotations-invalid-test",
            "exam_mode": "part_practice",
            "part_numbers": [1],
            "annotations": [wrong_test],
        },
    )
    assert mismatch.status_code == 200
    assert mismatch.json()["result"]["annotations"] == []
    assert mismatch.json()["result"]["annotation_warnings"][0]["code"] == "annotation_test_mismatch_ignored"


def test_empty_note_annotation_is_ignored_without_blocking_submission(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SESSION_DB_PATH", str(tmp_path / "empty-note.sqlite3"))
    client = TestClient(app)
    annotation = _annotation()
    annotation["note"] = "   "
    response = client.post(
        "/api/v1/sessions/submit",
        json={
            "test_id": "b10-test-a",
            "client_submission_id": "annotations-empty-note",
            "exam_mode": "part_practice",
            "part_numbers": [1],
            "annotations": [annotation],
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["annotations"] == []
    assert response.json()["result"]["annotation_warnings"][0]["code"] == "invalid_annotation_ignored"
