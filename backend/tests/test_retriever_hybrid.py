"""Hybrid retriever (vector + BM25 + RRF) tests with fakes."""

from app.rag.retriever import search_knowledge


def test_hybrid_search_fuses_dense_and_sparse(monkeypatch):
    class _Emb:
        def embed_query(self, q):
            return [0.1, 0.2]

    class _Store:
        def search(self, vector, top_k=5, doc_type=None):
            return [
                {"chunk_id": "c_vec", "score": 0.2},
                {"chunk_id": "c_both", "score": 0.3},
            ]

    class _Bm25:
        def search(self, query, top_k=5, doc_type=None):
            return [
                {"chunk_id": "c_bm25", "score": 8.0},
                {"chunk_id": "c_both", "score": 6.0},
            ]

        def size(self):
            return 3

    class _Chunk:
        def __init__(self, cid, doc_id, doc_type, content):
            self.id = cid
            self.doc_id = doc_id
            self.doc_type = doc_type
            self.chunk_index = 0
            self.content = content

    class _Doc:
        def __init__(self, did, title, path):
            self.id = did
            self.title = title
            self.source_path = path

    chunks = {
        "c_vec": _Chunk("c_vec", "d1", "sop", "向量独有"),
        "c_bm25": _Chunk("c_bm25", "d2", "refund", "关键词独有 全额退款"),
        "c_both": _Chunk("c_both", "d3", "pricing", "双路命中"),
    }
    docs = {
        "d1": _Doc("d1", "SOP", "sop.md"),
        "d2": _Doc("d2", "退款", "refund.md"),
        "d3": _Doc("d3", "定价", "pricing.md"),
    }

    def fake_hydrate(chunk_ids):
        return (
            {cid: chunks[cid] for cid in chunk_ids if cid in chunks},
            {did: docs[did] for did in {chunks[c].doc_id for c in chunk_ids if c in chunks}},
        )

    monkeypatch.setattr("app.rag.retriever.get_settings", lambda: type("S", (), {
        "rag_hybrid_enabled": True,
        "rag_candidate_k": 10,
        "rag_rrf_k": 60,
        "rag_rerank_enabled": False,
        "rag_rerank_top_n": 10,
    })())
    monkeypatch.setattr("app.rag.retriever.get_embedding_client", lambda: _Emb())
    monkeypatch.setattr("app.rag.retriever.get_vector_store", lambda: _Store())
    monkeypatch.setattr("app.rag.retriever.get_bm25_index", lambda: _Bm25())
    monkeypatch.setattr("app.rag.retriever._ensure_bm25_ready", lambda: None)
    monkeypatch.setattr("app.rag.retriever._hydrate_chunks", fake_hydrate)

    result = search_knowledge("全额退款", top_k=3)
    assert result["ok"] is True
    assert result.get("mode") == "hybrid"
    ids = [h["chunk_id"] for h in result["hits"]]
    assert "c_both" in ids
    assert len(ids) <= 3
    # dual-hit should rank first under RRF
    assert ids[0] == "c_both"


def test_vector_only_mode(monkeypatch):
    class _Emb:
        def embed_query(self, q):
            return [0.1]

    class _Store:
        def search(self, vector, top_k=5, doc_type=None):
            return [{"chunk_id": "c1", "score": 0.1}]

    class _Chunk:
        id = "c1"
        doc_id = "d1"
        doc_type = "sop"
        chunk_index = 0
        content = "内容"

    class _Doc:
        id = "d1"
        title = "T"
        source_path = "t.md"

    monkeypatch.setattr("app.rag.retriever.get_settings", lambda: type("S", (), {
        "rag_hybrid_enabled": False,
        "rag_candidate_k": 10,
        "rag_rrf_k": 60,
        "rag_rerank_enabled": False,
        "rag_rerank_top_n": 10,
    })())
    monkeypatch.setattr("app.rag.retriever.get_embedding_client", lambda: _Emb())
    monkeypatch.setattr("app.rag.retriever.get_vector_store", lambda: _Store())
    monkeypatch.setattr(
        "app.rag.retriever._hydrate_chunks",
        lambda ids: ({"c1": _Chunk()}, {"d1": _Doc()}),
    )

    result = search_knowledge("测试", top_k=5, mode="vector")
    assert result["ok"] is True
    assert result.get("mode") == "vector"
    assert result["hits"][0]["chunk_id"] == "c1"
