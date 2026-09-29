"""Auth API: login / me / logout."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.deps import AuthUser, get_current_user
from app.core.db import session_scope
from app.core.response import fail, ok
from app.core.security import create_access_token, verify_password
from app.models.user import SysUser
from app.services.auth_users import ensure_demo_users

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


@router.post("/login")
def login(body: LoginRequest) -> dict:
    ensure_demo_users()
    username = body.username.strip()
    with session_scope() as db:
        row = db.scalar(select(SysUser).where(SysUser.username == username))
        if not row or int(row.status) != 1:
            return fail(401, "用户名或密码错误")
        if not verify_password(body.password, row.password_hash):
            return fail(401, "用户名或密码错误")
        token = create_access_token(user_id=row.id, username=row.username, role=row.role)
        return ok(
            {
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": row.id,
                    "username": row.username,
                    "display_name": row.display_name,
                    "role": row.role,
                },
            }
        )


@router.get("/me")
def me(user: Annotated[AuthUser, Depends(get_current_user)]) -> dict:
    return ok(user.to_dict())


@router.post("/logout")
def logout(user: Annotated[AuthUser, Depends(get_current_user)]) -> dict:
    return ok({"ok": True, "username": user.username})
