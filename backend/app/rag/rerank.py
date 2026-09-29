"""Optional cross-encoder / API rerank over candidate hits."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def rerank_hits(
    query: str,
    hits: list[dict[str, Any]],
    *,
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """Rerank hits via OpenAI-compatible / DashScope-style rerank API.

    On any failure or when disabled, returns ``hits`` unchanged (fail-open).
    """
    settings = get_settings()
    if not getattr(settings, "rag_rerank_enabled", False):
        return hits
    if not hits:
        return hits

    base = (getattr(settings, "resolved_rerank_base_url", "") or "").rstrip("/")
    key = getattr(settings, "resolved_rerank_api_key", "") or ""
    model = getattr(settings, "rerank_model", "") or ""
    if not base or not key or not model:
        return hits

    limit = top_n if top_n is not None else len(hits)
    candidates = hits[: max(1, limit)]
    documents = [(h.get("content") or "")[:4000] for h in candidates]

    # Prefer OpenAI-compatible style; also try DashScope documents/rerank shape fallbacks
    url = f"{base}/reranks" if not base.endswith("/reranks") else base
    payload = {
        "model": model,
        "query": query,
        "documents": documents,
        "top_n": len(documents),
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                # DashScope compatible-mode sometimes uses /rerank
                alt = f"{base}/rerank"
                resp = client.post(alt, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("rerank failed, keep original order: %s", exc)
        return hits

    results = data.get("results") or data.get("output", {}).get("results") or []
    if not results:
        return hits

    ordered: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in results:
        idx = item.get("index")
        if idx is None:
            continue
        try:
            i = int(idx)
        except (TypeError, ValueError):
            continue
        if i < 0 or i >= len(candidates) or i in seen:
            continue
        seen.add(i)
        row = dict(candidates[i])
        score = item.get("relevance_score", item.get("score"))
        if score is not None:
            row["rerank_score"] = float(score)
            row["score"] = float(score)
        ordered.append(row)

    # append any missing candidates in original order
    for i, h in enumerate(candidates):
        if i not in seen:
            ordered.append(h)
    return ordered
