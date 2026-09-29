"""FastAPI auth dependencies."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Header

from app.core.db import session_scope
from app.core.security import AuthError, decode_access_token
from app.models.user import SysUser


class AuthUser:
    def __init__(self, user_id: str, username: str, display_name: str, role: str):
        self.id = user_id
        self.username = username
        self.display_name = display_name
        self.role = role

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
        }


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise AuthError("未登录")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AuthError("未登录")
    return parts[1].strip()


def get_current_user(authorization: Annotated[str | None, Header()] = None) -> AuthUser:
    token = _extract_bearer(authorization)
    payload = decode_access_token(token)
    user_id = str(payload.get("sub") or "")
    if not user_id:
        raise AuthError("无效的登录凭证")
    with session_scope() as db:
        row = db.get(SysUser, user_id)
        if not row or int(row.status) != 1:
            raise AuthError("用户不存在或已禁用")
        return AuthUser(
            user_id=row.id,
            username=row.username,
            display_name=row.display_name,
            role=row.role,
        )


def require_roles(*roles: str):
    allowed = set(roles)

    def _dep(user: Annotated[AuthUser, Depends(get_current_user)]) -> AuthUser:
        if user.role not in allowed:
            raise AuthError("无权限执行该操作", status_code=403)
        return user

    return _dep
