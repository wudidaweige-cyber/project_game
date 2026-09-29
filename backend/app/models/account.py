from sqlalchemy import Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base


class OpsAccount(Base, AuditMixin):
    __tablename__ = "ops_account"
    __table_args__ = {"comment": "租赁账号"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID")
    game_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="游戏ID")
    account_code: Mapped[str] = mapped_column(String(128), nullable=False, comment="业务账号标识")
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0, comment="租赁价格")
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="available/rented/offline/frozen")
    rent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="累计出租次数")
