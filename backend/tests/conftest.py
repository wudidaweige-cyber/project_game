"""Shared pytest fixtures for authenticated API tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_users import ensure_demo_users


@pytest.fixture(scope="session")
def auth_token() -> str:
    ensure_demo_users()
    client = TestClient(app)
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "operator", "password": "Operator@123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    return body["data"]["access_token"]


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_client(client: TestClient, auth_headers: dict[str, str]) -> TestClient:
    """TestClient that injects Authorization on every request."""

    class _Authed:
        def __init__(self, inner: TestClient, headers: dict[str, str]):
            self._inner = inner
            self._headers = headers

        def request(self, method: str, url: str, **kwargs):
            headers = dict(kwargs.pop("headers", {}) or {})
            headers.update(self._headers)
            return self._inner.request(method, url, headers=headers, **kwargs)

        def get(self, url: str, **kwargs):
            return self.request("GET", url, **kwargs)

        def post(self, url: str, **kwargs):
            return self.request("POST", url, **kwargs)

    return _Authed(client, auth_headers)  # type: ignore[return-value]
