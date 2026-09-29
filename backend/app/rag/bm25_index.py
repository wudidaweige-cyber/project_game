"""In-memory BM25 over knowledge chunks (Chinese-friendly tokenization)."""

from __future__ import annotations

import math
import re
import threading
from typing import Any

_ASCII_RE = re.compile(r"[A-Za-z0-9_]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """Lightweight tokenizer: ASCII words + CJK bigrams (avoid noisy unigrams)."""
    raw = (text or "").strip().lower()
    if not raw:
        return []
    tokens: list[str] = []
    for m in _ASCII_RE.finditer(raw):
        tokens.append(m.group(0))
    for m in _CJK_RE.finditer(raw):
        span = m.group(0)
        if len(span) == 1:
            tokens.append(span)
        else:
            # bigrams only — unigrams cause false hits on common chars
            tokens.extend(span[i : i + 2] for i in range(len(span) - 1))
    return tokens


class Bm25Index:
    """Okapi BM25 over an in-memory chunk corpus."""

    def __init__(self, *, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._lock = threading.RLock()
        self._chunk_ids: list[str] = []
        self._doc_types: list[str] = []
        self._tokenized: list[list[str]] = []
        self._doc_len: list[int] = []
        self._avgdl = 0.0
        self._df: dict[str, int] = {}
        self._tf: list[dict[str, int]] = []
        self._n = 0

    def clear(self) -> None:
        with self._lock:
            self._chunk_ids = []
            self._doc_types = []
            self._tokenized = []
            self._doc_len = []
            self._avgdl = 0.0
            self._df = {}
            self._tf = []
            self._n = 0

    def build(self, chunks: list[dict[str, Any]]) -> None:
        """Replace index contents. Each chunk: chunk_id, content, optional doc_type."""
        chunk_ids: list[str] = []
        doc_types: list[str] = []
        tokenized: list[list[str]] = []
        doc_len: list[int] = []
        tf_list: list[dict[str, int]] = []
        df: dict[str, int] = {}

        for ch in chunks:
            cid = str(ch.get("chunk_id") or "").strip()
            if not cid:
                continue
            tokens = tokenize(str(ch.get("content") or ""))
            freqs: dict[str, int] = {}
            for t in tokens:
                freqs[t] = freqs.get(t, 0) + 1
            chunk_ids.append(cid)
            doc_types.append(str(ch.get("doc_type") or ""))
            tokenized.append(tokens)
            doc_len.append(len(tokens))
            tf_list.append(freqs)
            for term in freqs:
                df[term] = df.get(term, 0) + 1

        n = len(chunk_ids)
        avgdl = (sum(doc_len) / n) if n else 0.0
        with self._lock:
            self._chunk_ids = chunk_ids
            self._doc_types = doc_types
            self._tokenized = tokenized
            self._doc_len = doc_len
            self._avgdl = avgdl
            self._df = df
            self._tf = tf_list
            self._n = n

    def size(self) -> int:
        with self._lock:
            return self._n

    def _idf(self, term: str) -> float:
        # Robertson-Sparck Jones IDF with +0.5 smoothing
        df = self._df.get(term, 0)
        return math.log(1.0 + (self._n - df + 0.5) / (df + 0.5))

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        doc_type: str | None = None,
    ) -> list[dict[str, Any]]:
        q_tokens = tokenize(query)
        if not q_tokens or top_k <= 0:
            return []
        with self._lock:
            if self._n == 0:
                return []
            scores: list[tuple[float, str]] = []
            for i, cid in enumerate(self._chunk_ids):
                if doc_type and self._doc_types[i] != doc_type:
                    continue
                score = 0.0
                dl = self._doc_len[i] or 1
                tf = self._tf[i]
                for term in q_tokens:
                    freq = tf.get(term)
                    if not freq:
                        continue
                    idf = self._idf(term)
                    denom = freq + self.k1 * (1.0 - self.b + self.b * dl / (self._avgdl or 1.0))
                    score += idf * (freq * (self.k1 + 1.0)) / denom
                if score > 0:
                    scores.append((score, cid))
            scores.sort(key=lambda x: x[0], reverse=True)
            return [{"chunk_id": cid, "score": sc} for sc, cid in scores[:top_k]]


_INDEX: Bm25Index | None = None
_INDEX_LOCK = threading.Lock()


def get_bm25_index() -> Bm25Index:
    global _INDEX
    with _INDEX_LOCK:
        if _INDEX is None:
            _INDEX = Bm25Index()
        return _INDEX


def rebuild_bm25_from_db() -> int:
    """Load published chunks from PostgreSQL into the process-local BM25 index."""
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker

    from app.core.db import get_engine
    from app.models import OpsKnowledgeChunk, OpsKnowledgeDoc

    SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    rows: list[dict[str, Any]] = []
    with SessionLocal() as session:
        docs = {
            d.id: d
            for d in session.execute(
                select(OpsKnowledgeDoc).where(OpsKnowledgeDoc.status == "published")
            ).scalars().all()
        }
        chunks = session.execute(select(OpsKnowledgeChunk)).scalars().all()
        for c in chunks:
            if c.doc_id not in docs:
                continue
            rows.append(
                {
                    "chunk_id": c.id,
                    "doc_type": c.doc_type,
                    "content": c.content,
                }
            )
    index = get_bm25_index()
    index.build(rows)
    return index.size()
