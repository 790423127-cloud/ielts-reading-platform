from __future__ import annotations

import csv
import io
import json

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.vocabulary_repository import VocabularyRepository


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("SESSION_DB_PATH", str(tmp_path / "vocabulary.sqlite3"))
    return TestClient(app)


def vocabulary_repository_for_test(tmp_path) -> VocabularyRepository:
    return VocabularyRepository(tmp_path / "vocabulary.sqlite3")


def test_same_term_merges_while_distinct_sources_are_preserved(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    first = client.post(
        "/api/v1/vocabulary",
        json={
            "term": "Substantial",
            "meaning": "大量的；重要的",
            "source_type": "reading_text",
            "source_sentence": "A substantial proportion of residents supported the plan.",
            "test_title": "剑雅10 Test A",
            "part_number": 2,
        },
    )
    assert first.status_code == 200
    assert first.json()["occurrence_count"] == 1
    assert first.json()["deduplicated"] is False

    duplicate_source = client.post(
        "/api/v1/vocabulary",
        json={
            "term": " substantial ",
            "meaning": "不应覆盖现有释义",
            "source_type": "reading_text",
            "source_sentence": "A substantial proportion of residents supported the plan.",
            "test_title": "剑雅10 Test A",
            "part_number": 2,
        },
    )
    assert duplicate_source.status_code == 200
    assert duplicate_source.json()["id"] == first.json()["id"]
    assert duplicate_source.json()["deduplicated"] is True
    assert duplicate_source.json()["source_added"] is False
    assert duplicate_source.json()["occurrence_count"] == 1
    assert duplicate_source.json()["meaning"] == "大量的；重要的"

    second_source = client.post(
        "/api/v1/vocabulary",
        json={
            "term": "SUBSTANTIAL",
            "source_type": "wrong_review",
            "source_sentence": "There was substantial evidence for the conclusion.",
            "source_question_id": "q-8",
        },
    )
    assert second_source.status_code == 200
    data = second_source.json()
    assert data["id"] == first.json()["id"]
    assert data["source_added"] is True
    assert data["occurrence_count"] == 2
    assert len(data["sources"]) == 2


def test_update_delete_and_user_isolation(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    created = client.post(
        "/api/v1/vocabulary",
        json={"term": "allocate", "note": "初始笔记", "source_type": "manual"},
    ).json()

    update = client.put(
        f"/api/v1/vocabulary/{created['id']}",
        json={
            "meaning": "分配；拨给",
            "note": "常见搭配：allocate resources",
            "status": "mastered",
        },
    )
    assert update.status_code == 200
    assert update.json()["meaning"] == "分配；拨给"
    assert update.json()["status"] == "mastered"

    owner_list = client.get("/api/v1/vocabulary")
    other_list = client.get("/api/v1/vocabulary?user_id=other")
    assert owner_list.json()["count"] == 1
    assert owner_list.json()["mastered_count"] == 1
    assert other_list.json()["count"] == 0

    forbidden_update = client.put(
        f"/api/v1/vocabulary/{created['id']}",
        json={"user_id": "other", "meaning": "x", "note": "", "status": "learning"},
    )
    assert forbidden_update.status_code == 404

    deleted = client.delete(f"/api/v1/vocabulary/{created['id']}")
    assert deleted.status_code == 200
    assert client.get("/api/v1/vocabulary").json()["count"] == 0


def test_csv_txt_json_exports_are_downloadable_and_safe(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    client.post(
        "/api/v1/vocabulary",
        json={
            "term": "=unsafe",
            "meaning": "+formula-like meaning",
            "note": "复习",
            "source_type": "sentence",
            "source_sentence": "The word appeared in a saved sentence.",
        },
    )

    csv_response = client.get("/api/v1/vocabulary/export?format=csv")
    assert csv_response.status_code == 200
    assert "attachment" in csv_response.headers["content-disposition"]
    assert csv_response.content.startswith("\ufeff".encode("utf-8"))
    parsed = list(csv.reader(io.StringIO(csv_response.text.lstrip("\ufeff"))))
    assert parsed[0][0] == "单词/词组"
    assert parsed[1][0] == "'=unsafe"
    assert parsed[1][1] == "'+formula-like meaning"

    client.post(
        "/api/v1/vocabulary",
        json={"term": "allocate", "meaning": "分配", "source_type": "manual"},
    )
    txt_response = client.get("/api/v1/vocabulary/export?format=txt")
    assert txt_response.status_code == 200
    assert txt_response.headers["content-type"].startswith("text/plain")
    lines = txt_response.text.splitlines()
    assert len(lines) == 2
    assert set(lines) == {"=unsafe", "allocate"}
    assert all(line and line.strip() == line for line in lines)
    assert "IELTS 阅读词汇本" not in txt_response.text
    assert "释义：" not in txt_response.text
    assert "状态：" not in txt_response.text
    assert "来源：" not in txt_response.text

    json_response = client.get("/api/v1/vocabulary/export?format=json")
    assert json_response.status_code == 200
    exported = json.loads(json_response.text)
    assert exported["version"] == 1
    assert exported["count"] == 2
    assert {item["term"] for item in exported["items"]} == {"=unsafe", "allocate"}


def test_selected_and_unexported_txt_exports_track_export_state(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    first = client.post(
        "/api/v1/vocabulary",
        json={"term": "allocate", "source_type": "manual"},
    ).json()
    second = client.post(
        "/api/v1/vocabulary",
        json={"term": "substantial", "source_type": "manual"},
    ).json()

    selected = client.post(
        "/api/v1/vocabulary/export",
        json={"item_ids": [first["id"]], "only_unexported": False},
    )
    assert selected.status_code == 200
    assert selected.text == "allocate"

    items = {
        item["id"]: item
        for item in client.get("/api/v1/vocabulary").json()["items"]
    }
    assert items[first["id"]]["exported_before"] is True
    assert items[second["id"]]["exported_before"] is False

    unexported = client.post(
        "/api/v1/vocabulary/export",
        json={"item_ids": [], "only_unexported": True},
    )
    assert unexported.status_code == 200
    assert unexported.text == "substantial"
    assert unexported.text.splitlines() == ["substantial"]

    empty = client.post(
        "/api/v1/vocabulary/export",
        json={"item_ids": [], "only_unexported": True},
    )
    assert empty.status_code == 409

    reexport_selected = client.post(
        "/api/v1/vocabulary/export",
        json={"item_ids": [first["id"]], "only_unexported": False},
    )
    assert reexport_selected.status_code == 200
    assert reexport_selected.text == "allocate"


def test_paraphrase_txt_exports_track_export_state(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    repository = vocabulary_repository_for_test(tmp_path)
    first = repository.capture_paraphrase(
        user_id="owner",
        payload={
            "question_phrase": "more than five colours",
            "source_phrase": "designer colours",
            "note": "题目与原文表达对照",
            "confidence": 0.91,
            "source_session_id": "s1",
            "source_question_id": "q2",
            "test_title": "剑雅5 Test A",
            "part_number": 1,
        },
    )
    second = repository.capture_paraphrase(
        user_id="owner",
        payload={
            "question_phrase": "cost less than",
            "source_phrase": "under $10",
            "confidence": 0.88,
            "source_session_id": "s2",
            "source_question_id": "q1",
            "test_title": "剑雅5 Test A",
            "part_number": 1,
        },
    )

    selected = client.post(
        "/api/v1/vocabulary/paraphrases/export",
        json={"item_ids": [first["id"]], "only_unexported": False},
    )
    assert selected.status_code == 200
    assert selected.text == "more than five colours = designer colours"

    items = {
        item["id"]: item
        for item in client.get("/api/v1/vocabulary/paraphrases").json()["items"]
    }
    assert items[first["id"]]["exported_before"] is True
    assert items[second["id"]]["exported_before"] is False

    unexported = client.post(
        "/api/v1/vocabulary/paraphrases/export",
        json={"item_ids": [], "only_unexported": True},
    )
    assert unexported.status_code == 200
    assert unexported.text == "cost less than = under $10"


def test_paraphrase_json_export_preserves_learning_context(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    repository = vocabulary_repository_for_test(tmp_path)
    item = repository.capture_paraphrase(
        user_id="owner",
        payload={
            "question_phrase": "cost less than",
            "source_phrase": "under $10",
            "note": "价格上限替换",
            "confidence": 0.93,
            "source_session_id": "session-json",
            "source_question_id": "q9",
            "test_id": "cambridge-9",
            "test_title": "剑雅9 Test 1",
            "part_number": 2,
            "question_number": "9",
            "question_prompt": "Which option costs less than ten dollars?",
            "evidence": "Every item in this section is under $10.",
            "user_answer": "B",
            "correct_answer": "C",
        },
    )

    response = client.post(
        "/api/v1/vocabulary/paraphrases/export",
        json={
            "item_ids": [item["id"]],
            "only_unexported": False,
            "format": "json",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"].endswith('.json"')
    package = response.json()
    assert package["schemaVersion"] == 1
    assert package["source"] == "ielts-reading-coach"
    assert package["count"] == 1
    exported = package["items"][0]
    assert exported["id"] == item["id"]
    assert exported["questionPhrase"] == "cost less than"
    assert exported["sourcePhrase"] == "under $10"
    assert exported["occurrenceCount"] == 1
    assert exported["sources"][0]["evidence"] == "Every item in this section is under $10."
