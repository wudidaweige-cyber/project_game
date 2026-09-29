from sqlalchemy import SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base


class SysUser(Base, AuditMixin):
    __tablename__ = "sys_user"
    __table_args__ = {"comment": "系统用户"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID")
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment="登录名")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码哈希")
    display_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="显示名")
    role: Mapped[str] = mapped_column(String(32), nullable=False, comment="角色 admin/operator/analyst")
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="1启用0禁用")
