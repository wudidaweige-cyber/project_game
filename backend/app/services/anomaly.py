"""Metric anomaly detection over ops_daily_metric windows."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.mcp import db as mcp_db

# Relative change threshold for sum metrics; absolute for rate metrics.
REL_THRESHOLD = 0.15
RATE_ABS_THRESHOLD = 0.03

METRICS = (
    ("gmv", "sum", "GMV"),
    ("order_count", "sum", "订单量"),
    ("rent_rate", "avg", "出租率"),
    ("refund_rate", "avg", "退款率"),
)


def _agg_sql(metric: str, how: str) -> str:
    if how == "sum":
        return f"COALESCE(SUM({metric}), 0)"
    return f"COALESCE(AVG({metric}), 0)"


def _pct_change(cur: float, base: float) -> float | None:
    if base == 0:
        if cur == 0:
            return 0.0
        return None
    return (cur - base) / abs(base)


def _is_anomaly(metric: str, how: str, cur: float, base: float) -> tuple[bool, float | None]:
    change = _pct_change(cur, base)
    if how == "avg":
        delta = cur - base
        return abs(delta) >= RATE_ABS_THRESHOLD, change
    if change is None:
        return cur > 0, change
    return abs(change) >= REL_THRESHOLD, change


def _window_value(
    *,
    metric: str,
    how: str,
    start: date,
    end: date,
    game_id: str = "",
) -> float:
    expr = _agg_sql(metric, how)
    row = mcp_db.fetch_one(
        f"""
        SELECT {expr} AS v
        FROM ops_daily_metric
        WHERE metric_date >= :start AND metric_date <= :end
          AND game_id = :game_id
        """,
        {"start": start, "end": end, "game_id": game_id},
    )
    return float(row["v"]) if row and row.get("v") is not None else 0.0


def _game_deltas(
    *,
    metric: str,
    how: str,
    recent_start: date,
    recent_end: date,
    base_start: date,
    base_end: date,
    limit: int = 5,
) -> list[dict[str, Any]]:
    expr = _agg_sql(metric, how)
    # Avoid FULL OUTER JOIN for broader PG compatibility: union game ids then left join.
    rows = mcp_db.fetch_all(
        f"""
        WITH ids AS (
          SELECT DISTINCT game_id
          FROM ops_daily_metric
          WHERE game_id <> ''
            AND (
              (metric_date >= :rs AND metric_date <= :re)
              OR (metric_date >= :bs AND metric_date <= :be)
            )
        ),
        recent AS (
          SELECT game_id, {expr} AS v
          FROM ops_daily_metric
          WHERE metric_date >= :rs AND metric_date <= :re
            AND game_id <> ''
          GROUP BY game_id
        ),
        baseline AS (
          SELECT game_id, {expr} AS v
          FROM ops_daily_metric
          WHERE metric_date >= :bs AND metric_date <= :be
            AND game_id <> ''
          GROUP BY game_id
        )
        SELECT
          i.game_id AS game_id,
          g.name AS game_name,
          COALESCE(r.v, 0) AS recent_value,
          COALESCE(b.v, 0) AS baseline_value,
          (COALESCE(r.v, 0) - COALESCE(b.v, 0)) AS delta
        FROM ids i
        LEFT JOIN recent r ON r.game_id = i.game_id
        LEFT JOIN baseline b ON b.game_id = i.game_id
        LEFT JOIN ops_game g ON g.id = i.game_id
        ORDER BY ABS(COALESCE(r.v, 0) - COALESCE(b.v, 0)) DESC
        LIMIT :limit
        """,
        {
            "rs": recent_start,
            "re": recent_end,
            "bs": base_start,
            "be": base_end,
            "limit": limit,
        },
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        cur = float(row["recent_value"] or 0)
        base = float(row["baseline_value"] or 0)
        change = _pct_change(cur, base)
        out.append(
            {
                "game_id": row["game_id"],
                "game_name": row.get("game_name") or row["game_id"],
                "recent_value": cur,
                "baseline_value": base,
                "delta": float(row["delta"] or 0),
                "change_ratio": change,
            }
        )
    return out


def detect_metric_anomalies(
    *,
    window_days: int = 7,
    end_date: date | None = None,
    top_games: int = 5,
) -> dict[str, Any]:
    """Compare recent window vs previous equal window for platform + top games."""
    days = max(3, min(int(window_days), 30))
    end = end_date or date.today()
    recent_start = end - timedelta(days=days - 1)
    base_end = recent_start - timedelta(days=1)
    base_start = base_end - timedelta(days=days - 1)

    # Ensure there is any metric data in recent window
    sample = mcp_db.fetch_one(
        """
        SELECT COUNT(*) AS n
        FROM ops_daily_metric
        WHERE metric_date >= :start AND metric_date <= :end
        """,
        {"start": recent_start, "end": end},
    )
    if not sample or int(sample.get("n") or 0) == 0:
        return {
            "ok": True,
            "has_data": False,
            "window_days": days,
            "recent": {"start": recent_start.isoformat(), "end": end.isoformat()},
            "baseline": {"start": base_start.isoformat(), "end": base_end.isoformat()},
            "platform_alerts": [],
            "message": "最近时间窗口内没有可用的日指标数据，无法判断异常。",
        }

    alerts: list[dict[str, Any]] = []
    for metric, how, label in METRICS:
        cur = _window_value(metric=metric, how=how, start=recent_start, end=end, game_id="")
        base = _window_value(metric=metric, how=how, start=base_start, end=base_end, game_id="")
        is_abnormal, change = _is_anomaly(metric, how, cur, base)
        games = _game_deltas(
            metric=metric,
            how=how,
            recent_start=recent_start,
            recent_end=end,
            base_start=base_start,
            base_end=base_end,
            limit=top_games,
        )
        item = {
            "metric": metric,
            "label": label,
            "agg": how,
            "recent_value": cur,
            "baseline_value": base,
            "change_ratio": change,
            "is_anomaly": is_abnormal,
            "direction": "up" if cur > base else ("down" if cur < base else "flat"),
            "top_games": games,
        }
        if is_abnormal:
            alerts.append(item)

    return {
        "ok": True,
        "has_data": True,
        "window_days": days,
        "recent": {"start": recent_start.isoformat(), "end": end.isoformat()},
        "baseline": {"start": base_start.isoformat(), "end": base_end.isoformat()},
        "platform_alerts": alerts,
        "all_metrics": [
            {
                "metric": m,
                "label": lab,
                "recent_value": _window_value(
                    metric=m, how=h, start=recent_start, end=end, game_id=""
                ),
                "baseline_value": _window_value(
                    metric=m, how=h, start=base_start, end=base_end, game_id=""
                ),
            }
            for m, h, lab in METRICS
        ],
        "message": "" if alerts else "对比窗口内未检测到超过阈值的显著异常指标。",
    }
