"""Knowledge document list / upload / delete API tests."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_users import ensure_demo_users


client = TestClient(app)


class _FakeEmbed:
    dim = 8

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float((i + j) % 7) for j in range(self.dim)] for i, _ in enumerate(texts)]


class _FakeStore:
    def __init__(self):
        self.rows: list[dict] = []

    def ensure_collection(self, dim: int) -> None:
        self.dim = dim

    def drop_collection(self) -> None:
        self.rows = []

    def delete_by_chunk_ids(self, chunk_ids: list[str]) -> None:
        ids = set(chunk_ids)
        self.rows = [r for r in self.rows if r["chunk_id"] not in ids]

    def delete_by_doc_ids(self, doc_ids: list[str]) -> None:
        ids = set(doc_ids)
        self.rows = [r for r in self.rows if r["doc_id"] not in ids]

    def upsert(self, records: list[dict]) -> int:
        self.rows.extend(records)
        return len(records)

    def count(self) -> int:
        return len(self.rows)


def _admin_headers() -> dict[str, str]:
    ensure_demo_users()
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123"},
    ).json()
    return {"Authorization": f"Bearer {login['data']['access_token']}"}


def test_docs_list_forbidden_for_operator(auth_headers):
    resp = client.get("/api/v1/knowledge/docs", headers=auth_headers)
    assert resp.status_code == 403


def test_upload_list_delete_doc(monkeypatch, tmp_path):
    from app.core.config import get_settings

    kd = tmp_path / "knowledge"
    kd.mkdir()
    monkeypatch.setenv("KNOWLEDGE_DIR", str(kd))
    get_settings.cache_clear()

    fake_store = _FakeStore()
    monkeypatch.setattr("app.rag.ingest.get_embedding_client", lambda: _FakeEmbed())
    monkeypatch.setattr("app.rag.ingest.get_vector_store", lambda: fake_store)
    monkeypatch.setattr("app.rag.ingest._rebuild_bm25", lambda: (0, ""))

    headers = _admin_headers()
    content = "# 测试退款规则\n\n用户可在故障时申请全额退款。\n"
    resp = client.post(
        "/api/v1/knowledge/docs",
        headers=headers,
        files={"file": ("rule-refund-demo.md", content.encode("utf-8"), "text/markdown")},
        data={"doc_type": "refund"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["ok"] is True
    doc_id = body["data"]["document"]["id"]
    assert body["data"]["document"]["doc_type"] == "refund"
    assert body["data"]["chunk_count"] >= 1
    assert fake_store.count() >= 1
    assert (kd / "uploads" / "rule-refund-demo.md").exists()

    listed = client.get("/api/v1/knowledge/docs", headers=headers)
    assert listed.status_code == 200
    items = listed.json()["data"]["items"]
    assert any(i["id"] == doc_id for i in items)

    detail = client.get(f"/api/v1/knowledge/docs/{doc_id}", headers=headers)
    assert detail.status_code == 200
    assert len(detail.json()["data"]["chunks"]) >= 1

    deleted = client.delete(f"/api/v1/knowledge/docs/{doc_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted_id"] == doc_id
    assert fake_store.count() == 0
    get_settings.cache_clear()


def test_upload_rejects_non_md():
    headers = _admin_headers()
    resp = client.post(
        "/api/v1/knowledge/docs",
        headers=headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 400
