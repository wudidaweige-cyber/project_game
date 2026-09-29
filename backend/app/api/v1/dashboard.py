from datetime import date

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import get_engine
from app.core.response import ok
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _session() -> Session:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)()


@router.get("/overview")
def overview(
    start_date: date = Query(...),
    end_date: date = Query(...),
    game_id: str | None = Query(None),
) -> dict:
    with _session() as session:
        data = dashboard_service.get_overview(session, start_date, end_date, game_id)
    return ok(data)


@router.get("/trends")
def trends(
    metric: str = Query("gmv"),
    start_date: date = Query(...),
    end_date: date = Query(...),
    game_id: str | None = Query(None),
) -> dict:
    try:
        with _session() as session:
            data = dashboard_service.get_trends(session, metric, start_date, end_date, game_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(data)


@router.get("/game-rank")
def game_rank(
    metric: str = Query("gmv"),
    start_date: date = Query(...),
    end_date: date = Query(...),
    limit: int = Query(10, ge=1, le=50),
) -> dict:
    try:
        with _session() as session:
            data = dashboard_service.get_game_rank(session, metric, start_date, end_date, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(data)


@router.get("/games/{game_id}")
def game_detail(
    game_id: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
) -> dict:
    with _session() as session:
        data = dashboard_service.get_game_detail(session, game_id, start_date, end_date)
    if data is None:
        raise HTTPException(status_code=404, detail="game not found")
    return ok(data)
