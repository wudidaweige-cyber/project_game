"""Append recent demo orders/metrics up to today (does not wipe existing data).

Usage (from backend/):
  .\\.venv\\Scripts\\python -m scripts.seed_recent
  .\\.venv\\Scripts\\python -m scripts.seed_recent --days 30
"""

from __future__ import annotations

import argparse
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.models import OpsAccount, OpsDailyMetric, OpsGame, OpsOrder, OpsPlayer, OpsRefund


def _uid() -> str:
    return str(uuid.uuid4())


def _audit() -> dict:
    return {
        "create_user_id": "seed",
        "create_user_name": "seed-recent",
        "update_user_id": "seed",
        "update_user_name": "seed-recent",
    }


def _existing_metric_dates(session: Session) -> set[date]:
    rows = session.execute(select(OpsDailyMetric.metric_date).where(OpsDailyMetric.game_id == "")).all()
    return {r[0] for r in rows if r[0] is not None}


def seed_recent(session: Session, *, days: int | None = None) -> None:
    games = session.execute(select(OpsGame).where(OpsGame.status == 1)).scalars().all()
    players = session.execute(select(OpsPlayer).where(OpsPlayer.status == 1)).scalars().all()
    accounts = session.execute(select(OpsAccount)).scalars().all()
    if not games or not players or not accounts:
        raise SystemExit("缺少游戏/用户/账号基础数据，请先运行: python -m scripts.seed_demo")

    accounts_by_game: dict[str, list[OpsAccount]] = {}
    for a in accounts:
        accounts_by_game.setdefault(a.game_id, []).append(a)

    today = date.today()
    max_date = session.execute(select(func.max(OpsDailyMetric.metric_date))).scalar_one_or_none()
    if days is not None and days > 0:
        start = today - timedelta(days=days - 1)
    elif max_date is None:
        start = today - timedelta(days=59)
    else:
        start = max_date + timedelta(days=1)

    if start > today:
        print(f"已有数据到 {max_date}，无需补充（today={today}）")
        return

    have = _existing_metric_dates(session)
    last_order_no = session.execute(select(func.max(OpsOrder.order_no))).scalar_one_or_none() or ""
    # keep sequence unique enough
    order_seq = 1
    if last_order_no.startswith("ORD") and last_order_no[-5:].isdigit():
        order_seq = int(last_order_no[-5:]) + 1

    filled_days = 0
    added_orders = 0
    d = start
    while d <= today:
        if d in have:
            d += timedelta(days=1)
            continue

        day_index_from_end = (today - d).days
        for g in games:
            base_orders = random.randint(4, 14)
            if g.name == "原神" and day_index_from_end <= 14:
                base_orders = max(1, base_orders // 3)
            if g.name == "王者荣耀":
                base_orders += 4

            day_gmv = Decimal("0")
            day_orders = 0
            day_refunds = 0
            pool = accounts_by_game.get(g.id) or accounts
            for _ in range(base_orders):
                acc = random.choice(pool)
                player = random.choice(players)
                price = Decimal(str(acc.price))
                ot = datetime(
                    d.year,
                    d.month,
                    d.day,
                    random.randint(8, 22),
                    random.randint(0, 59),
                    tzinfo=timezone.utc,
                )
                oid = _uid()
                session.add(
                    OpsOrder(
                        id=oid,
                        order_no=f"ORD{d.strftime('%Y%m%d')}{order_seq:05d}",
                        player_id=player.id,
                        account_id=acc.id,
                        game_id=g.id,
                        price=price,
                        duration_hours=random.choice([12, 24, 48, 72]),
                        status="finished",
                        order_time=ot,
                        **_audit(),
                    )
                )
                order_seq += 1
                day_orders += 1
                day_gmv += price
                added_orders += 1

                if random.random() < (0.16 if g.name == "原神" and day_index_from_end <= 14 else 0.06):
                    session.add(
                        OpsRefund(
                            id=_uid(),
                            order_id=oid,
                            amount=price,
                            reason=random.choice(["账号异常", "体验不符", "误下单"]),
                            status="approved",
                            refund_time=ot + timedelta(hours=2),
                            **_audit(),
                        )
                    )
                    day_refunds += 1

            available = sum(1 for a in pool if a.status == "available")
            rented = sum(1 for a in pool if a.status == "rented")
            stock = max(available + rented, 1)
            rent_rate = Decimal(str(round(rented / stock, 4)))
            refund_rate = Decimal(str(round(day_refunds / max(day_orders, 1), 4)))
            session.add(
                OpsDailyMetric(
                    id=_uid(),
                    metric_date=d,
                    game_id=g.id,
                    gmv=day_gmv,
                    order_count=day_orders,
                    rent_rate=rent_rate,
                    refund_rate=refund_rate,
                    available_account_count=available,
                    active_game_count=0,
                    **_audit(),
                )
            )

        session.flush()
        game_rows = (
            session.execute(
                select(OpsDailyMetric).where(
                    OpsDailyMetric.metric_date == d,
                    OpsDailyMetric.game_id != "",
                )
            )
            .scalars()
            .all()
        )
        total_gmv = sum((r.gmv for r in game_rows), Decimal("0"))
        total_orders = sum(r.order_count for r in game_rows)
        avg_rent = (
            sum((r.rent_rate for r in game_rows), Decimal("0")) / len(game_rows)
            if game_rows
            else Decimal("0")
        )
        avg_refund = (
            sum((r.refund_rate for r in game_rows), Decimal("0")) / len(game_rows)
            if game_rows
            else Decimal("0")
        )
        avail = sum(r.available_account_count for r in game_rows)
        session.add(
            OpsDailyMetric(
                id=_uid(),
                metric_date=d,
                game_id="",
                gmv=total_gmv,
                order_count=total_orders,
                rent_rate=avg_rent.quantize(Decimal("0.0001")),
                refund_rate=avg_refund.quantize(Decimal("0.0001")),
                available_account_count=avail,
                active_game_count=len({r.game_id for r in game_rows}),
                **_audit(),
            )
        )
        filled_days += 1
        d += timedelta(days=1)

    session.commit()
    new_max = session.execute(select(func.max(OpsDailyMetric.metric_date))).scalar_one()
    print(
        f"seed_recent ok: filled_days={filled_days}, orders+={added_orders}, "
        f"range={start}~{today}, metric_max={new_max}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Append recent demo metrics/orders")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="强制补最近 N 天（已有日期会跳过）；默认从现有最大日期的次日补到今天",
    )
    args = parser.parse_args()
    engine = get_engine()
    with Session(engine) as session:
        seed_recent(session, days=args.days)


if __name__ == "__main__":
    main()
