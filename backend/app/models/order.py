from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base


class OpsOrder(Base, AuditMixin):
    __tablename__ = "ops_order"
    __table_args__ = {"comment": "租赁订单"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID")
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="订单号")
    player_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="玩家ID")
    account_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="账号ID")
    game_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="游戏ID")
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, comment="成交价")
    duration_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24, comment="租赁时长小时")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="pending/active/finished/cancelled/refunding"
    )
    order_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True, comment="下单时间")
