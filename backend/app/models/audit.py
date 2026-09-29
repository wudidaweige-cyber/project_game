from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SysAuditLog(Base):
    """Append-only audit log — no update_* audit mixin."""

    __tablename__ = "sys_audit_log"
    __table_args__ = {"comment": "操作审计日志"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID")
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="用户ID")
    action: Mapped[str] = mapped_column(String(128), nullable=False, comment="动作")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="详情")
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="创建时间"
    )
