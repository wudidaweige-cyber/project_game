"""BM25 in-memory index tests."""

from app.rag.bm25_index import Bm25Index, tokenize


def test_tokenize_keeps_chinese_and_ascii_terms():
    tokens = tokenize("全额退款 GMV 出租率")
    assert "退款" in "".join(tokens) or "全额" in tokens or any("退" in t for t in tokens)
    assert any(t.lower() == "gmv" for t in tokens)


def test_bm25_ranks_keyword_match_higher():
    index = Bm25Index()
    index.build(
        [
            {"chunk_id": "c1", "doc_type": "refund", "content": "支付后无法交付账号可申请全额退款。"},
            {"chunk_id": "c2", "doc_type": "pricing", "content": "高峰期可观察调价，禁止自动改价落库。"},
            {"chunk_id": "c3", "doc_type": "sop", "content": "异常订单升级客服主管处理。"},
        ]
    )
    hits = index.search("什么情况下可以全额退款", top_k=2)
    assert hits
    assert hits[0]["chunk_id"] == "c1"
    assert hits[0]["score"] > 0


def test_bm25_doc_type_filter():
    index = Bm25Index()
    index.build(
        [
            {"chunk_id": "c1", "doc_type": "refund", "content": "全额退款规则说明"},
            {"chunk_id": "c2", "doc_type": "risk", "content": "全额退款风控例外"},
        ]
    )
    hits = index.search("全额退款", top_k=5, doc_type="refund")
    assert [h["chunk_id"] for h in hits] == ["c1"]
