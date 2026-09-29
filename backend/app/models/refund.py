from datetime import datetime

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base


class OpsRefund(Base, AuditMixin):
    __tablename__ = "ops_refund"
    __table_args__ = {"comment": "退款单"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID")
    order_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="订单ID")
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, comment="退款金额")
    reason: Mapped[str] = mapped_column(String(256), nullable=False, default="", comment="退款原因")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="applying/approved/rejected")
    refund_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="退款时间")
