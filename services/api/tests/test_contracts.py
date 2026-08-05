from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.main import create_app


ROOT = Path(__file__).resolve().parents[3]


def test_generated_frontend_contract_matches_live_openapi() -> None:
    schema = create_app().openapi()
    canonical = json.dumps(
        schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    expected_hash = hashlib.sha256(canonical).hexdigest()
    saved_hash = (ROOT / "packages" / "contracts" / "openapi.sha256").read_text(
        encoding="ascii"
    ).strip()
    generated = (ROOT / "packages" / "contracts" / "src" / "generated.ts").read_text(
        encoding="utf-8"
    )

    assert saved_hash == expected_hash
    assert "HealthResponse:" in generated
    assert "SessionSubmitRequest:" in generated
    assert "SessionSummary:" in generated


def test_session_contract_exposes_the_transport_aliases_used_by_frontend() -> None:
    properties = create_app().openapi()["components"]["schemas"][
        "SessionSubmitRequest"
    ]["properties"]

    assert "partElapsedSeconds" in properties
    assert "questionElapsedSeconds" in properties
    assert "part_elapsed_seconds" not in properties
    assert "question_elapsed_seconds" not in properties
