"""Seed demo business data for dashboard / NL2SQL.

Usage (from backend/):
  .\\.venv\\Scripts\\python -m scripts.seed_demo
"""

from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, select

from app.core.db import get_engine
from app.models import (
    OpsAccount,
    OpsDailyMetric,
    OpsGame,
    OpsOrder,
    OpsPlayer,
    OpsRefund,
    SysUser,
)
from sqlalchemy.orm import Session

GAMES = [
    ("王者荣耀", "MOBA", "Mobile"),
    ("和平精英", "射击", "Mobile"),
    ("原神", "RPG", "Multi"),
    ("永劫无间", "动作", "PC"),
    ("英雄联盟", "MOBA", "PC"),
    ("CS2", "射击", "PC"),
]


def _uid() -> str:
    return str(uuid.uuid4())


def _audit() -> dict:
    return {
        "create_user_id": "seed",
        "create_user_name": "seed",
        "update_user_id": "seed",
        "update_user_name": "seed",
    }


def seed(session: Session) -> None:
    # clear business tables (keep sys if any)
    for model in (OpsRefund, OpsOrder, OpsAccount, OpsPlayer, OpsDailyMetric, OpsGame):
        session.execute(delete(model))
    session.execute(delete(SysUser).where(SysUser.username == "admin"))

    admin = SysUser(
        id=_uid(),
        username="admin",
        password_hash="dev-only-not-for-prod",
        display_name="管理员",
        role="admin",
        status=1,
        **_audit(),
    )
    session.add(admin)

    games: list[OpsGame] = []
    for name, category, platform in GAMES:
        g = OpsGame(
            id=_uid(),
            name=name,
            category=category,
            platform=platform,
            status=1,
            **_audit(),
        )
        games.append(g)
        session.add(g)
    session.flush()

    players: list[OpsPlayer] = []
    now = datetime.now(timezone.utc)
    for i in range(40):
        p = OpsPlayer(
            id=_uid(),
            user_code=f"U{10000 + i}",
            user_type="normal" if i % 5 else "vip",
            register_time=now - timedelta(days=random.randint(10, 200)),
            status=1,
            mobile_mask=f"138****{i:04d}",
            **_audit(),
        )
        players.append(p)
        session.add(p)
    session.flush()

    accounts: list[OpsAccount] = []
    for g in games:
        for j in range(12):
            status = random.choice(["available", "available", "rented", "offline"])
            a = OpsAccount(
                id=_uid(),
                game_id=g.id,
                account_code=f"{g.name[:2]}-{j+1:03d}",
                price=Decimal(str(round(random.uniform(8, 80), 2))),
                status=status,
                rent_count=random.randint(0, 40),
                **_audit(),
            )
            accounts.append(a)
            session.add(a)
    session.flush()

    accounts_by_game: dict[str, list[OpsAccount]] = {}
    for a in accounts:
        accounts_by_game.setdefault(a.game_id, []).append(a)

    # ~60 days of orders
    start = date.today() - timedelta(days=59)
    order_seq = 1
    for day_offset in range(60):
        d = start + timedelta(days=day_offset)
        # inject a dip for one game in last 15 days (for anomaly/demo)
        for g in games:
            base_orders = random.randint(3, 12)
            if g.name == "原神" and day_offset >= 45:
                base_orders = max(1, base_orders // 3)
            if g.name == "王者荣耀":
                base_orders += 4

            day_gmv = Decimal("0")
            day_orders = 0
            day_refunds = 0
            for _ in range(base_orders):
                acc = random.choice(accounts_by_game[g.id])
                player = random.choice(players)
                price = Decimal(str(acc.price))
                ot = datetime(d.year, d.month, d.day, random.randint(8, 22), random.randint(0, 59), tzinfo=timezone.utc)
                oid = _uid()
                order = OpsOrder(
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
                session.add(order)
                order_seq += 1
                day_orders += 1
                day_gmv += price

                if random.random() < (0.18 if g.name == "原神" and day_offset >= 45 else 0.06):
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

            available = sum(1 for a in accounts_by_game[g.id] if a.status == "available")
            rented = sum(1 for a in accounts_by_game[g.id] if a.status == "rented")
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

        # site-wide rollup for the day
        rows = session.execute(
            select(OpsDailyMetric).where(
                OpsDailyMetric.metric_date == d,
                OpsDailyMetric.game_id != "",
            )
        ).scalars().all()
        # above query won't see unflushed; compute from what we just added via flush
        session.flush()
        game_rows = session.execute(
            select(OpsDailyMetric).where(
                OpsDailyMetric.metric_date == d,
                OpsDailyMetric.game_id != "",
            )
        ).scalars().all()
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

    session.commit()
    print(
        f"seed ok: games={len(games)}, players={len(players)}, "
        f"accounts={len(accounts)}, days=60"
    )


def main() -> None:
    engine = get_engine()
    with Session(engine) as session:
        seed(session)


if __name__ == "__main__":
    main()
