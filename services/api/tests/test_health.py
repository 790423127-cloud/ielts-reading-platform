from fastapi.testclient import TestClient

from app.main import app


def test_health_does_not_connect_database() -> None:
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["databaseConnected"] is False
    assert payload["features"]["nextAppRouter"] is True
    assert payload["features"]["legacyHashRouter"] is False
