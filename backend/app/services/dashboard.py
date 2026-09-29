from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import OpsDailyMetric, OpsGame


def _site_filter(stmt: Select, game_id: str | None) -> Select:
    if game_id:
        return stmt.where(OpsDailyMetric.game_id == game_id)
    return stmt.where(OpsDailyMetric.game_id == "")


def get_overview(session: Session, start_date: date, end_date: date, game_id: str | None = None) -> dict:
    stmt = select(
        func.coalesce(func.sum(OpsDailyMetric.gmv), 0),
        func.coalesce(func.sum(OpsDailyMetric.order_count), 0),
        func.coalesce(func.avg(OpsDailyMetric.rent_rate), 0),
        func.coalesce(func.avg(OpsDailyMetric.refund_rate), 0),
        func.coalesce(func.avg(OpsDailyMetric.available_account_count), 0),
        func.coalesce(func.max(OpsDailyMetric.active_game_count), 0),
    ).where(
        OpsDailyMetric.metric_date >= start_date,
        OpsDailyMetric.metric_date <= end_date,
    )
    stmt = _site_filter(stmt, game_id)
    gmv, orders, rent, refund, avail, active = session.execute(stmt).one()
    return {
        "gmv": float(gmv or 0),
        "order_count": int(orders or 0),
        "rent_rate": float(rent or 0),
        "refund_rate": float(refund or 0),
        "available_account_count": int(round(float(avail or 0))),
        "active_game_count": int(active or 0),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "game_id": game_id,
    }


def get_trends(
    session: Session,
    metric: str,
    start_date: date,
    end_date: date,
    game_id: str | None = None,
) -> dict:
    allowed = {
        "gmv": OpsDailyMetric.gmv,
        "order_count": OpsDailyMetric.order_count,
        "rent_rate": OpsDailyMetric.rent_rate,
        "refund_rate": OpsDailyMetric.refund_rate,
    }
    if metric not in allowed:
        raise ValueError(f"unsupported metric: {metric}")

    col = allowed[metric]
    stmt = (
        select(OpsDailyMetric.metric_date, col)
        .where(
            OpsDailyMetric.metric_date >= start_date,
            OpsDailyMetric.metric_date <= end_date,
        )
        .order_by(OpsDailyMetric.metric_date.asc())
    )
    stmt = _site_filter(stmt, game_id)
    rows = session.execute(stmt).all()
    return {
        "metric": metric,
        "points": [
            {"date": d.isoformat(), "value": float(v if v is not None else 0)}
            for d, v in rows
        ],
    }


def get_game_rank(
    session: Session,
    metric: str,
    start_date: date,
    end_date: date,
    limit: int = 10,
) -> dict:
    agg_map = {
        "gmv": func.sum(OpsDailyMetric.gmv),
        "order_count": func.sum(OpsDailyMetric.order_count),
        "rent_rate": func.avg(OpsDailyMetric.rent_rate),
        "refund_rate": func.avg(OpsDailyMetric.refund_rate),
    }
    if metric not in agg_map:
        raise ValueError(f"unsupported metric: {metric}")

    value_col = agg_map[metric].label("metric_value")
    stmt = (
        select(
            OpsDailyMetric.game_id,
            OpsGame.name,
            value_col,
        )
        .join(OpsGame, OpsGame.id == OpsDailyMetric.game_id)
        .where(
            OpsDailyMetric.metric_date >= start_date,
            OpsDailyMetric.metric_date <= end_date,
            OpsDailyMetric.game_id != "",
        )
        .group_by(OpsDailyMetric.game_id, OpsGame.name)
        .order_by(value_col.desc())
        .limit(limit)
    )
    rows = session.execute(stmt).all()
    return {
        "metric": metric,
        "items": [
            {
                "game_id": gid,
                "game_name": name,
                "value": float(val if val is not None else 0),
            }
            for gid, name, val in rows
        ],
    }


def get_game_detail(session: Session, game_id: str, start_date: date, end_date: date) -> dict | None:
    game = session.get(OpsGame, game_id)
    if game is None:
        return None
    overview = get_overview(session, start_date, end_date, game_id=game_id)
    trends = get_trends(session, "gmv", start_date, end_date, game_id=game_id)
    return {
        "game": {
            "id": game.id,
            "name": game.name,
            "category": game.category,
            "platform": game.platform,
            "status": game.status,
        },
        "overview": overview,
        "gmv_trends": trends["points"],
    }
