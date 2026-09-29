from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuditMixin:
    create_user_id: Mapped[str] = mapped_column(String(36), nullable=False, default="system", comment="创建人ID")
    create_user_name: Mapped[str] = mapped_column(String(64), nullable=False, default="system", comment="创建人名称")
    update_user_id: Mapped[str] = mapped_column(String(36), nullable=False, default="system", comment="更新人ID")
    update_user_name: Mapped[str] = mapped_column(String(64), nullable=False, default="system", comment="更新人名称")
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="创建时间"
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )
