"""Knowledge retrieval: vector / hybrid (BM25+RRF) / optional rerank."""

from __future__ import annotations

import logging
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.db import get_engine
from app.models import OpsKnowledgeChunk, OpsKnowledgeDoc
from app.rag.bm25_index import get_bm25_index, rebuild_bm25_from_db, tokenize
from app.rag.embeddings import get_embedding_client
from app.rag.rerank import rerank_hits
from app.rag.rrf import rrf_fuse
from app.rag.vector_store import get_vector_store

logger = logging.getLogger(__name__)

SearchMode = Literal["auto", "vector", "hybrid"]

_NO_HIT_MESSAGE = "无检索结果"
_MIN_LEXICAL_OVERLAP = 0.18


def _lexical_overlap(query: str, content: str) -> float:
    q_tokens = set(tokenize(query))
    if not q_tokens:
        return 0.0
    c_tokens = set(tokenize(content or ""))
    return len(q_tokens & c_tokens) / len(q_tokens)


def _filter_by_overlap(query: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop weak lexical matches so unrelated questions can surface as no-hit."""
    q_tokens = set(tokenize(query))
    # short / vague queries: skip gate to avoid over-filtering
    if len(q_tokens) < 4:
        return hits
    kept = [
        h
        for h in hits
        if _lexical_overlap(query, h.get("content") or "") >= _MIN_LEXICAL_OVERLAP
    ]
    return kept


def _hydrate_chunks(
    chunk_ids: list[str],
) -> tuple[dict[str, OpsKnowledgeChunk], dict[str, OpsKnowledgeDoc]]:
    if not chunk_ids:
        return {}, {}
    SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    with SessionLocal() as session:
        chunks = session.execute(
            select(OpsKnowledgeChunk).where(OpsKnowledgeChunk.id.in_(chunk_ids))
        ).scalars().all()
        by_id = {c.id: c for c in chunks}
        doc_ids = list({c.doc_id for c in chunks})
        docs = session.execute(
            select(OpsKnowledgeDoc).where(OpsKnowledgeDoc.id.in_(doc_ids))
        ).scalars().all()
        doc_by_id = {d.id: d for d in docs}
    return by_id, doc_by_id


def _ensure_bm25_ready() -> None:
    index = get_bm25_index()
    if index.size() > 0:
        return
    try:
        n = rebuild_bm25_from_db()
        logger.info("BM25 index loaded from DB: %s chunks", n)
    except Exception as exc:  # noqa: BLE001
        logger.warning("BM25 rebuild skipped: %s", exc)


def _enrich(
    ordered_ids: list[str],
    score_by_id: dict[str, float],
    by_id: dict[str, OpsKnowledgeChunk],
    doc_by_id: dict[str, OpsKnowledgeDoc],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for cid in ordered_ids:
        chunk = by_id.get(cid)
        if not chunk:
            continue
        doc = doc_by_id.get(chunk.doc_id)
        enriched.append(
            {
                "chunk_id": cid,
                "score": score_by_id.get(cid),
                "doc_id": chunk.doc_id,
                "doc_type": chunk.doc_type,
                "title": doc.title if doc else "",
                "source_path": doc.source_path if doc else "",
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
            }
        )
    return enriched


def search_knowledge(
    query: str,
    top_k: int = 5,
    doc_type: str | None = None,
    *,
    mode: SearchMode | None = None,
) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "查询为空", "hits": [], "mode": mode or "auto"}

    settings = get_settings()
    hybrid_default = bool(getattr(settings, "rag_hybrid_enabled", True))
    resolved_mode: SearchMode
    if mode in ("vector", "hybrid"):
        resolved_mode = mode
    else:
        resolved_mode = "hybrid" if hybrid_default else "vector"

    candidate_k = max(top_k, int(getattr(settings, "rag_candidate_k", 20) or 20))
    rrf_k = int(getattr(settings, "rag_rrf_k", 60) or 60)

    embedder = get_embedding_client()
    store = get_vector_store()
    vector = embedder.embed_query(q)
    dense_hits = store.search(vector, top_k=candidate_k, doc_type=doc_type)

    sparse_hits: list[dict[str, Any]] = []
    if resolved_mode == "hybrid":
        _ensure_bm25_ready()
        sparse_hits = get_bm25_index().search(q, top_k=candidate_k, doc_type=doc_type)

    if resolved_mode == "hybrid" and (dense_hits or sparse_hits):
        fused = rrf_fuse([dense_hits, sparse_hits], k=rrf_k, top_n=candidate_k)
        ordered_ids = [h["chunk_id"] for h in fused]
        score_by_id = {h["chunk_id"]: float(h.get("rrf_score") or 0.0) for h in fused}
    else:
        ordered_ids = [h["chunk_id"] for h in dense_hits if h.get("chunk_id")]
        score_by_id = {
            h["chunk_id"]: float(h.get("score") or 0.0)
            for h in dense_hits
            if h.get("chunk_id")
        }
        resolved_mode = "vector" if resolved_mode != "hybrid" else resolved_mode
        if resolved_mode == "hybrid" and not ordered_ids:
            # both empty
            pass

    if not ordered_ids:
        return {
            "ok": True,
            "error": "",
            "hits": [],
            "message": _NO_HIT_MESSAGE,
            "mode": resolved_mode,
        }

    by_id, doc_by_id = _hydrate_chunks(ordered_ids)
    enriched = _enrich(ordered_ids, score_by_id, by_id, doc_by_id)
    enriched = _filter_by_overlap(q, enriched)

    reranked = False
    if getattr(settings, "rag_rerank_enabled", True) and enriched:
        before = [h.get("chunk_id") for h in enriched]
        rerank_n = int(getattr(settings, "rag_rerank_top_n", 10) or 10)
        enriched = rerank_hits(q, enriched, top_n=max(top_k, rerank_n))
        after = [h.get("chunk_id") for h in enriched]
        reranked = before != after or any(h.get("rerank_score") is not None for h in enriched)

    hits = enriched[:top_k]
    if not hits:
        return {
            "ok": True,
            "error": "",
            "hits": [],
            "message": _NO_HIT_MESSAGE,
            "mode": resolved_mode,
        }

    return {
        "ok": True,
        "error": "",
        "hits": hits,
        "mode": resolved_mode,
        "dense_count": len(dense_hits),
        "sparse_count": len(sparse_hits),
        "reranked": reranked,
    }
