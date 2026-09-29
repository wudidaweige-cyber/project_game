"""Reciprocal Rank Fusion for hybrid retrieval."""

from __future__ import annotations

from typing import Any


def rrf_fuse(
    rank_lists: list[list[dict[str, Any]]],
    *,
    k: int = 60,
    top_n: int = 10,
    id_key: str = "chunk_id",
) -> list[dict[str, Any]]:
    """Fuse multiple ranked lists by Reciprocal Rank Fusion.

    Each item must contain ``id_key``. Scores from source lists are ignored;
    only rank position matters: ``1 / (k + rank)`` with rank starting at 1.
    """
    scores: dict[str, float] = {}
    meta: dict[str, dict[str, Any]] = {}
    for ranked in rank_lists:
        if not ranked:
            continue
        for rank, item in enumerate(ranked, start=1):
            cid = item.get(id_key)
            if not cid:
                continue
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            if cid not in meta:
                meta[cid] = {id_key: cid}
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)[: max(0, top_n)]
    return [{**meta[cid], "rrf_score": score} for cid, score in ordered]
