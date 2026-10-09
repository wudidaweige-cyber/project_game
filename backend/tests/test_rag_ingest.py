"""Ingest pipeline test with mocked embeddings (no live API / Milvus required)."""

from pathlib import Path

from app.rag.ingest import ingest_knowledge_dir


class _FakeEmbed:
    dim = 8

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float((i + j) % 7) for j in range(self.dim)] for i, _ in enumerate(texts)]


class _FakeStore:
    def __init__(self):
        self.rows = []

    def ensure_collection(self, dim: int) -> None:
        self.dim = dim

    def drop_collection(self) -> None:
        self.rows = []

    def delete_by_chunk_ids(self, chunk_ids: list[str]) -> None:
        self.rows = [r for r in self.rows if r["chunk_id"] not in chunk_ids]

    def delete_by_doc_ids(self, doc_ids: list[str]) -> None:
        self.rows = [r for r in self.rows if r["doc_id"] not in doc_ids]

    def upsert(self, records: list[dict]) -> int:
        self.rows.extend(records)
        return len(records)

    def count(self) -> int:
        return len(self.rows)


def test_ingest_knowledge_dir_writes_pg_and_vectors(monkeypatch, tmp_path: Path):
    # prepare mini knowledge dir
    kd = tmp_path / "knowledge"
    kd.mkdir()
    (kd / "rule-refund.md").write_text("# 退款规则\n\n用户可在故障时申请全额退款。\n", encoding="utf-8")
    (kd / "sop-account-listing.md").write_text("# 上架SOP\n\n账号质检通过后上架。\n", encoding="utf-8")

    fake_store = _FakeStore()
    monkeypatch.setattr("app.rag.ingest.get_embedding_client", lambda: _FakeEmbed())
    monkeypatch.setattr("app.rag.ingest.get_vector_store", lambda: fake_store)
    monkeypatch.setattr("app.rag.ingest._rebuild_bm25", lambda: (0, ""))

    result = ingest_knowledge_dir(kd)
    assert result["ok"] is True
    assert result["doc_count"] == 2
    assert result["chunk_count"] >= 2
    assert fake_store.count() == result["chunk_count"]


def test_ingest_markdown_document_single(monkeypatch):
    from app.rag.ingest import ingest_markdown_document

    fake_store = _FakeStore()
    monkeypatch.setattr("app.rag.ingest.get_embedding_client", lambda: _FakeEmbed())
    monkeypatch.setattr("app.rag.ingest.get_vector_store", lambda: fake_store)
    monkeypatch.setattr("app.rag.ingest._rebuild_bm25", lambda: (1, ""))

    result = ingest_markdown_document(
        filename="rule-pricing.md",
        content="# 定价\n\n高峰可上浮 10%。\n",
        doc_type="pricing",
        source_path="upload:rule-pricing.md",
    )
    assert result["ok"] is True
    assert result["document"]["doc_type"] == "pricing"
    assert result["chunk_count"] >= 1
    assert fake_store.count() == result["chunk_count"]
