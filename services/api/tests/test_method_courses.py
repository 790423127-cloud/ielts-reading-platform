from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.method_courses import SUBTYPE_METHODS, build_method_catalog
from app.main import app


def test_method_catalog_has_five_foundations_and_all_seventeen_subtypes() -> None:
    catalog = build_method_catalog()
    foundations = [item for item in catalog if item["kind"] == "foundation"]
    subtypes = [item for item in catalog if item["kind"] == "subtype"]

    assert len(foundations) == 5
    assert len(subtypes) == 17
    assert {item["subtype"] for item in subtypes} == set(SUBTYPE_METHODS)
    assert len({item["id"] for item in catalog}) == 22
    for item in catalog:
        assert item["title"]
        assert item["objective"]
        assert len(item["steps"]) >= 4
        assert len(item["traps"]) >= 3
        assert len(item["checklist"]) >= 3


def test_method_api_is_fixed_offline_content() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/methods")
    assert response.status_code == 200
    data = response.json()
    assert data["foundation_count"] == 5
    assert data["subtype_count"] == 17
    assert data["ai_calls"] == 0

    detail = client.get("/api/v1/methods/subtype-true_false_not_given")
    assert detail.status_code == 200
    assert detail.json()["subtype"] == "true_false_not_given"
