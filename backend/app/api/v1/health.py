from fastapi import APIRouter

from app.core.config import get_settings
from app.core.db import check_database
from app.core.response import ok

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    db = check_database()
    return ok(
        {
            "status": "ok",
            "app_env": settings.app_env,
            "database": db,
        }
    )
