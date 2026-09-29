"""Auth API tests."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_users import ensure_demo_users

client = TestClient(app)


def test_login_success():
    ensure_demo_users()
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "operator", "password": "Operator@123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["access_token"]
    assert body["data"]["user"]["role"] == "operator"


def test_login_wrong_password():
    ensure_demo_users()
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "operator", "password": "wrong"},
    )
    assert resp.json()["code"] == 401


def test_me_requires_token():
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == 401


def test_me_with_token(auth_headers):
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "operator"


def test_dashboard_requires_auth():
    resp = client.get(
        "/api/v1/dashboard/overview",
        params={"start_date": "2026-09-01", "end_date": "2026-09-22"},
    )
    assert resp.status_code == 401


def test_dashboard_with_auth(auth_headers):
    resp = client.get(
        "/api/v1/dashboard/overview",
        params={"start_date": "2026-09-01", "end_date": "2026-09-22"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 200


def test_ingest_forbidden_for_operator(auth_headers):
    resp = client.post("/api/v1/knowledge/ingest", headers=auth_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == 403


def test_ingest_allowed_for_admin():
    ensure_demo_users()
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123"},
    ).json()
    token = login["data"]["access_token"]
    # Do not actually re-ingest vectors in CI-like run if heavy; just assert not 403.
    # Calling ingest may be slow; skip body check if LLM/embedding unavailable.
    resp = client.post(
        "/api/v1/knowledge/ingest",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code != 403
