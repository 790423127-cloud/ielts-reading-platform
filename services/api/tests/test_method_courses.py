from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.legacy_method_courses import build_method_course_catalog
from app.domain.method_courses import build_foundation_catalog
from app.main import app


def test_method_catalog_has_five_foundations_and_all_seventeen_subtypes() -> None:
    foundations = build_foundation_catalog()
    subtypes = build_method_course_catalog()["courses"]

    assert len(foundations) == 5
    assert len(subtypes) == 17
    assert len({item["id"] for item in [*foundations, *subtypes]}) == 22
    for item in foundations:
        assert item["title"]
        assert item["objective"]
        assert len(item["steps"]) >= 4
        assert len(item["traps"]) >= 3
        assert len(item["checklist"]) >= 3
    for item in subtypes:
        assert item["title"]
        assert item["summary"]
        assert item["section_count"] == 12


def test_method_api_is_fixed_offline_content() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/methods")
    assert response.status_code == 200
    data = response.json()
    assert data["foundation_count"] == 5
    assert data["subtype_count"] == 17
    assert data["ai_calls"] == 0
    assert len(data["items"]) == 22
    assert len({item["id"] for item in data["items"]}) == 22

    detail = client.get("/api/v1/methods/subtype-true_false_not_given")
    assert detail.status_code == 200
    assert detail.json()["subtype"] == "true_false_not_given"
    assert detail.json()["section_count"] == 12
    assert detail.json()["standard_method"]
