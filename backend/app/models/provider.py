from sqlalchemy import SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base


class SysProvider(Base, AuditMixin):
    __tablename__ = "sys_provider"
    __table_args__ = {"comment": "模型厂商配置"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="显示名")
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="llm/embedding/rerank")
    base_url: Mapped[str] = mapped_column(String(512), nullable=False, comment="接口地址")
    api_key_enc: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="加密后的API Key")
    model_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="模型名")
    is_default: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="是否默认")
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="状态")
