"""MCP tool implementations — business readonly queries."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.mcp import db as mcp_db
from app.mcp.sql_guard import SqlGuardError


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": ""}


def _err(message: str) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": message}


def list_games(limit: int = 50, status: int | None = 1) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    if status is None:
        rows = mcp_db.fetch_all(
            """
            SELECT id, name, category, platform, status
            FROM ops_game
            ORDER BY name
            LIMIT :limit
            """,
            {"limit": limit},
        )
    else:
        rows = mcp_db.fetch_all(
            """
            SELECT id, name, category, platform, status
            FROM ops_game
            WHERE status = :status
            ORDER BY name
            LIMIT :limit
            """,
            {"status": status, "limit": limit},
        )
    return _ok(rows)


def query_gmv(start_date: str, end_date: str, game_id: str | None = None) -> dict[str, Any]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        return _err("日期格式须为 YYYY-MM-DD")

    if game_id:
        row = mcp_db.fetch_one(
            """
            SELECT
              COALESCE(SUM(gmv), 0) AS gmv,
              COALESCE(SUM(order_count), 0) AS order_count
            FROM ops_daily_metric
            WHERE metric_date >= :start AND metric_date <= :end
              AND game_id = :game_id
            """,
            {"start": start, "end": end, "game_id": game_id},
        )
    else:
        row = mcp_db.fetch_one(
            """
            SELECT
              COALESCE(SUM(gmv), 0) AS gmv,
              COALESCE(SUM(order_count), 0) AS order_count
            FROM ops_daily_metric
            WHERE metric_date >= :start AND metric_date <= :end
              AND game_id = ''
            """,
            {"start": start, "end": end},
        )
    data = {
        "start_date": start_date,
        "end_date": end_date,
        "game_id": game_id,
        "gmv": float(row["gmv"]) if row else 0.0,
        "order_count": int(row["order_count"]) if row else 0,
    }
    return _ok(data)


def query_rent_rate(start_date: str, end_date: str, game_id: str | None = None) -> dict[str, Any]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        return _err("日期格式须为 YYYY-MM-DD")

    if game_id:
        row = mcp_db.fetch_one(
            """
            SELECT
              COALESCE(AVG(rent_rate), 0) AS rent_rate,
              COALESCE(AVG(refund_rate), 0) AS refund_rate
            FROM ops_daily_metric
            WHERE metric_date >= :start AND metric_date <= :end
              AND game_id = :game_id
            """,
            {"start": start, "end": end, "game_id": game_id},
        )
    else:
        row = mcp_db.fetch_one(
            """
            SELECT
              COALESCE(AVG(rent_rate), 0) AS rent_rate,
              COALESCE(AVG(refund_rate), 0) AS refund_rate
            FROM ops_daily_metric
            WHERE metric_date >= :start AND metric_date <= :end
              AND game_id = ''
            """,
            {"start": start, "end": end},
        )
    data = {
        "start_date": start_date,
        "end_date": end_date,
        "game_id": game_id,
        "rent_rate": float(row["rent_rate"]) if row else 0.0,
        "refund_rate": float(row["refund_rate"]) if row else 0.0,
    }
    return _ok(data)


def query_orders_summary(
    start_date: str,
    end_date: str,
    game_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        return _err("日期格式须为 YYYY-MM-DD")

    limit = max(1, min(int(limit), 100))
    params: dict[str, Any] = {"start": start, "end": end, "limit": limit}
    game_filter = ""
    if game_id:
        game_filter = "AND o.game_id = :game_id"
        params["game_id"] = game_id

    summary = mcp_db.fetch_one(
        f"""
        SELECT
          COUNT(*) AS order_count,
          COALESCE(SUM(o.price), 0) AS gmv
        FROM ops_order o
        WHERE o.order_time::date >= :start
          AND o.order_time::date <= :end
          {game_filter}
        """,
        params,
    )
    samples = mcp_db.fetch_all(
        f"""
        SELECT o.order_no, o.game_id, g.name AS game_name, o.price, o.status, o.order_time
        FROM ops_order o
        LEFT JOIN ops_game g ON g.id = o.game_id
        WHERE o.order_time::date >= :start
          AND o.order_time::date <= :end
          {game_filter}
        ORDER BY o.order_time DESC
        LIMIT :limit
        """,
        params,
    )
    # serialize datetime
    for row in samples:
        if row.get("order_time") is not None:
            row["order_time"] = row["order_time"].isoformat()
        if row.get("price") is not None:
            row["price"] = float(row["price"])

    return _ok(
        {
            "start_date": start_date,
            "end_date": end_date,
            "game_id": game_id,
            "order_count": int(summary["order_count"]) if summary else 0,
            "gmv": float(summary["gmv"]) if summary else 0.0,
            "samples": samples,
        }
    )


def query_game_metric_rank(
    metric: str,
    start_date: str,
    end_date: str,
    limit: int = 10,
) -> dict[str, Any]:
    allowed = {"gmv", "order_count", "rent_rate", "refund_rate"}
    if metric not in allowed:
        return _err(f"metric 仅支持: {', '.join(sorted(allowed))}")
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        return _err("日期格式须为 YYYY-MM-DD")

    limit = max(1, min(int(limit), 50))
    if metric in {"gmv", "order_count"}:
        agg = f"SUM(m.{metric})"
    else:
        agg = f"AVG(m.{metric})"

    # metric is validated against allowlist — safe interpolation
    rows = mcp_db.fetch_all(
        f"""
        SELECT m.game_id, g.name AS game_name, {agg} AS value
        FROM ops_daily_metric m
        JOIN ops_game g ON g.id = m.game_id
        WHERE m.metric_date >= :start
          AND m.metric_date <= :end
          AND m.game_id <> ''
        GROUP BY m.game_id, g.name
        ORDER BY value DESC
        LIMIT :limit
        """,
        {"start": start, "end": end, "limit": limit},
    )
    for row in rows:
        row["value"] = float(row["value"] or 0)
    return _ok({"metric": metric, "start_date": start_date, "end_date": end_date, "items": rows})


def run_readonly_sql(sql: str, max_rows: int = 100) -> dict[str, Any]:
    try:
        rows = mcp_db.run_select(sql, max_rows=max_rows)
    except SqlGuardError as exc:
        return _err(str(exc))
    except Exception as exc:  # noqa: BLE001
        return _err(f"查询执行失败: {exc}")

    # json-friendly
    for row in rows:
        for k, v in list(row.items()):
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()
            elif type(v).__name__ == "Decimal":
                row[k] = float(v)
    return _ok({"row_count": len(rows), "rows": rows})
