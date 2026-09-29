"""Readonly DB helpers for MCP tools."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from app.mcp.sql_guard import validate_readonly_sql

_readonly_engine: Engine | None = None


def get_readonly_engine() -> Engine:
    global _readonly_engine
    if _readonly_engine is None:
        settings = get_settings()
        _readonly_engine = create_engine(
            settings.readonly_database_url,
            pool_pre_ping=True,
            pool_size=3,
            max_overflow=5,
        )
    return _readonly_engine


def fetch_all(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    engine = get_readonly_engine()
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        return [dict(row._mapping) for row in result]


def fetch_one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def run_select(sql: str, params: dict[str, Any] | None = None, max_rows: int = 200) -> list[dict[str, Any]]:
    safe = validate_readonly_sql(sql)
    # wrap limit if not present — simple safeguard
    upper = safe.upper()
    if " LIMIT " not in upper:
        safe = f"{safe} LIMIT {int(max_rows)}"
    return fetch_all(safe, params)
