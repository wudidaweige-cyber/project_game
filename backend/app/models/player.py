from datetime import datetime

from sqlalchemy import DateTime, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base


class OpsPlayer(Base, AuditMixin):
    __tablename__ = "ops_player"
    __table_args__ = {"comment": "平台C端用户"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID")
    user_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="业务用户号")
    user_type: Mapped[str] = mapped_column(String(32), nullable=False, default="normal", comment="用户类型")
    register_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="注册时间")
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="状态")
    mobile_mask: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="脱敏手机号")
