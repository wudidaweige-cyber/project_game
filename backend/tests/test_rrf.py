"""RRF fusion tests."""

from app.rag.rrf import rrf_fuse


def test_rrf_fuse_prefers_items_ranked_high_in_both_lists():
    dense = [{"chunk_id": "a", "score": 0.9}, {"chunk_id": "b", "score": 0.8}, {"chunk_id": "c", "score": 0.7}]
    sparse = [{"chunk_id": "b", "score": 12.0}, {"chunk_id": "a", "score": 10.0}, {"chunk_id": "d", "score": 5.0}]
    fused = rrf_fuse([dense, sparse], k=60, top_n=3)
    ids = [x["chunk_id"] for x in fused]
    assert ids[0] in ("a", "b")
    assert "a" in ids and "b" in ids
    assert len(fused) == 3
    assert all("rrf_score" in x for x in fused)


def test_rrf_fuse_single_list_preserves_order():
    only = [{"chunk_id": "x"}, {"chunk_id": "y"}]
    fused = rrf_fuse([only], k=60, top_n=10)
    assert [x["chunk_id"] for x in fused] == ["x", "y"]


def test_rrf_fuse_ignores_empty_lists():
    fused = rrf_fuse([[], [{"chunk_id": "z"}]], top_n=5)
    assert [x["chunk_id"] for x in fused] == ["z"]
