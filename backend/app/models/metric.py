from datetime import date

from sqlalchemy import Date, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base


class OpsDailyMetric(Base, AuditMixin):
    __tablename__ = "ops_daily_metric"
    __table_args__ = (
        UniqueConstraint("metric_date", "game_id", name="uk_ops_daily_metric_date_game"),
        {"comment": "日运营指标"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID")
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True, comment="指标日期")
    game_id: Mapped[str] = mapped_column(
        String(36), nullable=False, default="", index=True, comment="游戏ID，空字符串=全站"
    )
    gmv: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0, comment="GMV")
    order_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="订单量")
    rent_rate: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0, comment="出租率")
    refund_rate: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0, comment="退款率")
    available_account_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="可出租账号数")
    active_game_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="活跃游戏数")
