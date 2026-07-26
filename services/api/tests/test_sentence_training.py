from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.services.sentence_training import SentenceTrainingBank

API_ROOT = Path(__file__).resolve().parents[1]
TRAINING_ROOT = API_ROOT / "data" / "sentence-training"


def _assert_no_standard_answers(value: Any) -> None:
    forbidden = {
        "roles",
        "logic",
        "explanation",
        "simplified_zh",
        "answer_impact",
        "expected_answer",
    }
    if isinstance(value, dict):
        assert forbidden.isdisjoint(value.keys())
        for child in value.values():
            _assert_no_standard_answers(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_standard_answers(child)


def test_verified_sentence_training_file_matches_frozen_hash() -> None:
    bank = SentenceTrainingBank(TRAINING_ROOT)
    status = bank.validate()
    raw = (TRAINING_ROOT / "index.json").read_bytes()
    manifest = json.loads((TRAINING_ROOT / "migration_manifest.json").read_text("utf-8"))

    assert status["item_count"] == 30
    assert status["bytes"] == manifest["bytes"] == 22631
    assert status["sha256"] == manifest["sha256"]
    assert hashlib.sha256(raw).hexdigest() == "5601938dac22716eac75e852e3968fcd073ce23d772a12bdad3b0a55e45db291"
    assert status["source_git_blob_sha"] == "020b709a99c1e1169b01b05a98849bc7b6113af4"


def test_public_catalog_hides_verified_parse_until_submission() -> None:
    catalog = SentenceTrainingBank(TRAINING_ROOT).public_catalog()
    assert len(catalog["items"]) == 30
    assert len(catalog["steps"]) == 5
    assert catalog["answer_fields_exposed_before_submit"] is False
    assert catalog["ai_calls"] == 0
    _assert_no_standard_answers(catalog)


def test_fixed_sentence_training_is_server_scored_and_idempotent(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTENCE_TRAINING_DIR", str(TRAINING_ROOT))
    monkeypatch.setenv("SESSION_DB_PATH", str(tmp_path / "sentences.sqlite3"))
    bank = SentenceTrainingBank(TRAINING_ROOT)
    item = bank.items()[0]
    roles = item["roles"]
    official = {
        "predicate": roles.get("predicate") or "",
        "subject": roles.get("subject") or "",
        "object": roles.get("object") or "",
        "scope": roles.get("scope") or "",
        "logic": item.get("logic") or "none",
    }
    client = TestClient(app)

    response = client.post(
        "/api/v1/sentence-training/submit",
        json={
            "user_id": "owner",
            "client_submission_id": "sentence-training-0001",
            "item_id": item["id"],
            "answers": official,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["idempotent_replay"] is False
    assert data["result"]["score"] == data["result"]["total"] == 5
    assert data["result"]["verified_standard"] is True
    assert all(row["correct"] for row in data["result"]["steps"])
    assert all("expected_answer" in row for row in data["result"]["steps"])
    assert data["result"]["ai_calls"] == 0

    replay = client.post(
        "/api/v1/sentence-training/submit",
        json={
            "user_id": "owner",
            "client_submission_id": "sentence-training-0001",
            "item_id": item["id"],
            "answers": {},
        },
    )
    assert replay.status_code == 200
    replay_data = replay.json()
    assert replay_data["attempt_id"] == data["attempt_id"]
    assert replay_data["idempotent_replay"] is True
    assert replay_data["result"]["score"] == 5


def test_unexpected_fixed_training_analysis_key_is_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SENTENCE_TRAINING_DIR", str(TRAINING_ROOT))
    monkeypatch.setenv("SESSION_DB_PATH", str(tmp_path / "invalid-sentences.sqlite3"))
    item_id = SentenceTrainingBank(TRAINING_ROOT).items()[0]["id"]
    client = TestClient(app)
    response = client.post(
        "/api/v1/sentence-training/submit",
        json={
            "client_submission_id": "sentence-invalid-0001",
            "item_id": item_id,
            "answers": {"predicate": "x", "invented": "not allowed"},
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unexpected_analysis_keys"
