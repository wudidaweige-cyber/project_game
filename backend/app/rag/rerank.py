"""HTTP rerank over RAG candidates (DashScope / OpenAI-compatible)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def rerank_is_configured() -> bool:
    settings = get_settings()
    if not getattr(settings, "rag_rerank_enabled", True):
        return False
    base = (getattr(settings, "resolved_rerank_base_url", "") or "").rstrip("/")
    key = getattr(settings, "resolved_rerank_api_key", "") or ""
    model = getattr(settings, "rerank_model", "") or ""
    return bool(base and key and model)


def rerank_hits(
    query: str,
    hits: list[dict[str, Any]],
    *,
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """Rerank hits. Fail-open: return original order on any error or if disabled."""
    if not hits or not rerank_is_configured():
        return hits

    settings = get_settings()
    base = settings.resolved_rerank_base_url.rstrip("/")
    key = settings.resolved_rerank_api_key
    model = settings.rerank_model
    limit = top_n if top_n is not None else len(hits)
    candidates = hits[: max(1, limit)]
    documents = [(h.get("content") or "")[:4000] for h in candidates]

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payloads = [
        {"model": model, "query": query, "documents": documents, "top_n": len(documents)},
        {
            "model": model,
            "input": {"query": query, "documents": documents},
            "parameters": {"top_n": len(documents), "return_documents": False},
        },
    ]
    urls = []
    for path in ("/reranks", "/rerank"):
        urls.append(base + path if not base.endswith(path) else base)

    data: dict[str, Any] | None = None
    last_err = ""
    try:
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            for url in urls:
                for payload in payloads:
                    resp = client.post(url, json=payload, headers=headers)
                    if resp.status_code >= 400:
                        last_err = f"{resp.status_code} {resp.text[:180]}"
                        continue
                    data = resp.json()
                    break
                if data:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("rerank failed, keep original order: %s", exc)
        return hits

    if not data:
        logger.warning("rerank empty/error, keep original order: %s", last_err)
        return hits

    results = (
        data.get("results")
        or data.get("output", {}).get("results")
        or data.get("data", {}).get("results")
        or []
    )
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

    for i, h in enumerate(candidates):
        if i not in seen:
            ordered.append(h)
    return ordered
