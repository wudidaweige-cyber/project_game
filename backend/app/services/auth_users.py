"""Ensure demo admin/operator users exist for local auth."""

from __future__ import annotations

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import session_scope
from app.core.security import hash_password
from app.models.user import SysUser

OPERATOR_ID = "00000000-0000-4000-8000-000000000001"
ADMIN_ID = "00000000-0000-4000-8000-000000000002"

DEMO_USERS = (
    {
        "id": OPERATOR_ID,
        "username": "operator",
        "password": "Operator@123",
        "display_name": "演示运营",
        "role": "operator",
    },
    {
        "id": ADMIN_ID,
        "username": "admin",
        "password": "Admin@123",
        "display_name": "系统管理员",
        "role": "admin",
    },
)


def ensure_demo_users() -> list[dict]:
    """Upsert demo users; returns public user info (no password)."""
    out: list[dict] = []
    with session_scope() as db:
        for item in DEMO_USERS:
            row = db.get(SysUser, item["id"])
            if not row:
                by_name = db.scalar(select(SysUser).where(SysUser.username == item["username"]))
                if by_name:
                    row = by_name
            pwd_hash = hash_password(item["password"])
            if row:
                row.username = item["username"]
                row.password_hash = pwd_hash
                row.display_name = item["display_name"]
                row.role = item["role"]
                row.status = 1
                uid = row.id
            else:
                uid = item["id"]
                db.add(
                    SysUser(
                        id=uid,
                        username=item["username"],
                        password_hash=pwd_hash,
                        display_name=item["display_name"],
                        role=item["role"],
                        status=1,
                    )
                )
            out.append(
                {
                    "id": uid,
                    "username": item["username"],
                    "display_name": item["display_name"],
                    "role": item["role"],
                }
            )
        _ = get_settings().demo_user_id
    return out
