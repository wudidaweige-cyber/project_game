"""Optional HTTP rerank client tests."""

from app.rag.rerank import rerank_hits


def test_rerank_hits_reorders_by_relevance(monkeypatch):
    class _Resp:
        status_code = 200

        def json(self):
            return {
                "results": [
                    {"index": 1, "relevance_score": 0.95},
                    {"index": 0, "relevance_score": 0.10},
                ]
            }

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, headers=None):
            return _Resp()

    monkeypatch.setattr("app.rag.rerank.httpx.Client", _Client)
    monkeypatch.setattr(
        "app.rag.rerank.get_settings",
        lambda: type(
            "S",
            (),
            {
                "rag_rerank_enabled": True,
                "resolved_rerank_base_url": "https://example.com/v1",
                "resolved_rerank_api_key": "k",
                "rerank_model": "qwen3-rerank",
            },
        )(),
    )

    hits = [
        {"chunk_id": "a", "content": "低相关"},
        {"chunk_id": "b", "content": "高相关 全额退款"},
    ]
    out = rerank_hits("全额退款", hits, top_n=2)
    assert [h["chunk_id"] for h in out] == ["b", "a"]
    assert out[0].get("rerank_score") == 0.95


def test_rerank_disabled_returns_input(monkeypatch):
    monkeypatch.setattr(
        "app.rag.rerank.get_settings",
        lambda: type(
            "S",
            (),
            {
                "rag_rerank_enabled": False,
                "resolved_rerank_base_url": "",
                "resolved_rerank_api_key": "",
                "rerank_model": "",
            },
        )(),
    )
    hits = [{"chunk_id": "a", "content": "x"}]
    assert rerank_hits("q", hits) == hits
