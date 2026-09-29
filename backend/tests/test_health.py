"""Health API contract (fails until app is wired)."""

from fastapi.testclient import TestClient


def test_health_returns_unified_envelope():
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert "data" in body
    assert body["data"]["status"] == "ok"
    assert "app_env" in body["data"]
    assert "database" in body["data"]
