from sqlalchemy import SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base


class OpsGame(Base, AuditMixin):
    __tablename__ = "ops_game"
    __table_args__ = {"comment": "游戏主数据"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID")
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True, comment="游戏名")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="分类")
    platform: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="平台")
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="状态")
