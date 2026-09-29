"""Markdown chunking for knowledge ingest."""

from __future__ import annotations

import re
from typing import Any

_HEADING_RE = re.compile(r"(?m)^(#{1,3}\s+.+)$")


def chunk_markdown(text: str, max_chars: int = 500, overlap: int = 60) -> list[dict[str, Any]]:
    """Split markdown into overlapping text chunks.

    Prefer splitting on markdown headings; fall back to sliding windows.
    """
    raw = (text or "").strip()
    if not raw:
        return []

    sections: list[str] = []
    parts = _HEADING_RE.split(raw)
    buf = ""
    for part in parts:
        if not part:
            continue
        if _HEADING_RE.match(part):
            if buf.strip():
                sections.append(buf.strip())
            buf = part
        else:
            buf += part
    if buf.strip():
        sections.append(buf.strip())

    if not sections:
        sections = [raw]

    chunks: list[dict[str, Any]] = []
    idx = 0
    for section in sections:
        if len(section) <= max_chars:
            chunks.append(
                {
                    "chunk_index": idx,
                    "content": section,
                    "token_count": max(1, len(section) // 2),
                }
            )
            idx += 1
            continue
        start = 0
        while start < len(section):
            end = min(len(section), start + max_chars)
            piece = section[start:end].strip()
            if piece:
                chunks.append(
                    {
                        "chunk_index": idx,
                        "content": piece,
                        "token_count": max(1, len(piece) // 2),
                    }
                )
                idx += 1
            if end >= len(section):
                break
            start = max(end - overlap, start + 1)
    return chunks


def infer_doc_type(filename: str) -> str:
    name = filename.lower()
    if name.startswith("sop-") or "sop" in name:
        return "sop"
    if "refund" in name:
        return "refund"
    if "account" in name:
        return "account"
    if "pricing" in name or "price" in name:
        return "pricing"
    if "risk" in name:
        return "risk"
    return "other"


def infer_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip() or fallback
    return fallback
