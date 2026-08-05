from __future__ import annotations

import csv
import io
import json
import sqlite3

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


def test_repeated_manual_capture_tracks_frequency_without_duplicate_cards(
    monkeypatch, tmp_path
) -> None:
    client = _client(monkeypatch, tmp_path)
    payload = {
        "term": "Persistent",
        "meaning": "持续的；坚持不懈的",
        "source_type": "manual",
        "source_sentence": "A persistent learner keeps practising.",
    }

    first = client.post("/api/v1/vocabulary", json=payload).json()
    second = client.post(
        "/api/v1/vocabulary",
        json={**payload, "term": " persistent ", "meaning": "不覆盖原释义"},
    ).json()
    third = client.post("/api/v1/vocabulary", json=payload).json()

    assert first["manual_capture_count"] == 1
    assert second["id"] == first["id"]
    assert second["manual_capture_count"] == 2
    assert third["manual_capture_count"] == 3
    assert third["occurrence_count"] == 1
    assert len(third["sources"]) == 1
    assert third["meaning"] == "持续的；坚持不懈的"
    assert client.get("/api/v1/vocabulary").json()["count"] == 1


def test_vocabulary_v1_database_backfills_manual_capture_count(tmp_path) -> None:
    database = tmp_path / "legacy-vocabulary.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE schema_migrations (
            component TEXT PRIMARY KEY,
            version INTEGER NOT NULL,
            applied_at TEXT NOT NULL
        );
        INSERT INTO schema_migrations VALUES ('vocabulary', 1, '2026-08-01T00:00:00Z');
        CREATE TABLE vocabulary_items (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            term TEXT NOT NULL,
            term_norm TEXT NOT NULL,
            meaning TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'learning',
            occurrence_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, term_norm)
        );
        CREATE TABLE vocabulary_sources (
            id TEXT PRIMARY KEY,
            vocabulary_id TEXT NOT NULL,
            source_key TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_sentence TEXT,
            source_context TEXT,
            source_session_id TEXT,
            source_question_id TEXT,
            test_id TEXT,
            test_title TEXT,
            part_number INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(vocabulary_id, source_key)
        );
        INSERT INTO vocabulary_items VALUES (
            'word-1', 'owner', 'retain', 'retain', '', '', 'learning', 1,
            '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z'
        );
        INSERT INTO vocabulary_sources VALUES (
            'source-1', 'word-1', 'manual-key', 'manual', NULL, NULL, NULL, NULL,
            NULL, NULL, NULL, '2026-08-01T00:00:00Z'
        );
        """
    )
    connection.commit()
    connection.close()

    repository = VocabularyRepository(database)
    item = repository.list_items(user_id="owner")[0]

    assert item["manual_capture_count"] == 1
    connection = sqlite3.connect(database)
    try:
        version = connection.execute(
            "SELECT version FROM schema_migrations WHERE component = 'vocabulary'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert version == 2


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
    assert "手动记录次数" in parsed[0]
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
    allocate = next(item for item in exported["items"] if item["term"] == "allocate")
    assert allocate["manual_capture_count"] == 1


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
            "relation_type": "near-paraphrase",
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
    assert exported["relationType"] == "near-paraphrase"
    assert exported["occurrenceCount"] == 1
    assert exported["sources"][0]["evidence"] == "Every item in this section is under $10."


def test_smart_sync_is_incremental_and_only_acknowledges_unchanged_content(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    repository = vocabulary_repository_for_test(tmp_path)
    word = client.post(
        "/api/v1/vocabulary",
        json={"term": "retain", "meaning": "保留", "source_type": "manual"},
    ).json()
    pair = repository.capture_paraphrase(
        user_id="owner",
        payload={
            "question_phrase": "glow-worm distribution",
            "source_phrase": "spread around the globe",
            "relation_type": "near-paraphrase",
            "source_session_id": "session-1",
            "source_question_id": "q31",
        },
    )
    repository.mark_exported(user_id="owner", item_ids=[word["id"]])

    prepared = client.post("/api/v1/vocabulary/sync/prepare", json={}).json()
    assert prepared["type"] == "ielts-reading-coach-smart-sync"
    assert prepared["counts"] == {"words": 1, "paraphrases": 1}
    assert prepared["words"][0]["id"] == word["id"]
    assert prepared["words"][0]["manualCaptureCount"] == 1
    assert prepared["paraphrases"][0]["id"] == pair["id"]
    assert len(prepared["paraphrases"][0]["fingerprint"]) == 64

    receipt = {
        "transfer_id": prepared["transferId"],
        "words": [{
            "id": word["id"],
            "fingerprint": prepared["words"][0]["fingerprint"],
        }],
        "paraphrases": [{
            "id": pair["id"],
            "fingerprint": prepared["paraphrases"][0]["fingerprint"],
        }],
    }
    acknowledged = client.post(
        "/api/v1/vocabulary/sync/acknowledge",
        json=receipt,
    ).json()
    assert acknowledged["words_marked"] == 1
    assert acknowledged["paraphrases_marked"] == 1
    assert client.post("/api/v1/vocabulary/sync/prepare", json={}).json()["counts"] == {
        "words": 0,
        "paraphrases": 0,
    }

    changed = client.put(
        f"/api/v1/vocabulary/{word['id']}",
        json={"meaning": "保留；保持", "note": "已更新", "status": "learning"},
    )
    assert changed.status_code == 200
    changed_package = client.post("/api/v1/vocabulary/sync/prepare", json={}).json()
    assert changed_package["counts"] == {"words": 1, "paraphrases": 0}

    stale_ack = client.post(
        "/api/v1/vocabulary/sync/acknowledge",
        json={
            "transfer_id": changed_package["transferId"],
            "words": [{"id": word["id"], "fingerprint": "0" * 64}],
            "paraphrases": [],
        },
    ).json()
    assert stale_ack["words_marked"] == 0
    assert stale_ack["stale_word_ids"] == [word["id"]]
    assert client.post("/api/v1/vocabulary/sync/prepare", json={}).json()["counts"]["words"] == 1


def test_manual_export_does_not_suppress_first_smart_sync(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    repository = vocabulary_repository_for_test(tmp_path)
    word = client.post(
        "/api/v1/vocabulary",
        json={"term": "allocate", "source_type": "manual"},
    ).json()
    repository.mark_exported(user_id="owner", item_ids=[word["id"]])
    with repository._connect() as connection:
        connection.execute(
            "UPDATE vocabulary_exports SET content_fingerprint = '' WHERE vocabulary_id = ?",
            (word["id"],),
        )
        connection.commit()

    first = client.post("/api/v1/vocabulary/sync/prepare", json={}).json()
    second = client.post("/api/v1/vocabulary/sync/prepare", json={}).json()
    assert first["counts"]["words"] == 1
    assert second["counts"]["words"] == 1
