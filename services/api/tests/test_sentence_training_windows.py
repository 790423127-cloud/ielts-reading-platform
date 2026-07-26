from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.sentence_training import SentenceTrainingBank, SentenceTrainingDataError

API_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = API_ROOT / "data" / "sentence-training"


def test_windows_crlf_and_utf8_bom_keep_verified_manifest_valid(tmp_path) -> None:
    source = (SOURCE_ROOT / "index.json").read_bytes()
    windows_bytes = b"\xef\xbb\xbf" + source.replace(b"\n", b"\r\n")
    (tmp_path / "index.json").write_bytes(windows_bytes)
    (tmp_path / "migration_manifest.json").write_text(
        (SOURCE_ROOT / "migration_manifest.json").read_text("utf-8"),
        "utf-8",
    )

    status = SentenceTrainingBank(tmp_path).validate()
    manifest = json.loads((SOURCE_ROOT / "migration_manifest.json").read_text("utf-8"))
    assert status["verified"] is True
    assert status["checkout_normalized"] is True
    assert status["bytes"] == manifest["bytes"]
    assert status["sha256"] == manifest["sha256"]


def test_windows_normalization_does_not_hide_real_content_changes(tmp_path) -> None:
    source = (SOURCE_ROOT / "index.json").read_bytes().replace(b"\n", b"\r\n")
    changed = source.replace(b'"version": 1', b'"version": 2', 1)
    (tmp_path / "index.json").write_bytes(changed)
    (tmp_path / "migration_manifest.json").write_text(
        (SOURCE_ROOT / "migration_manifest.json").read_text("utf-8"),
        "utf-8",
    )

    with pytest.raises(SentenceTrainingDataError, match="SHA-256|byte count"):
        SentenceTrainingBank(tmp_path).validate()
