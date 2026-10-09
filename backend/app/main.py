from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.response import fail
from app.core.security import AuthError
from app.queue.jobs import start_worker_thread, stop_worker


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_worker_thread()
    yield
    stop_worker()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="游戏平台账号租赁智能运营分析系统",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.exception_handler(AuthError)
    async def _auth_error_handler(_request: Request, exc: AuthError):
        return JSONResponse(
            status_code=exc.status_code,
            content=fail(exc.status_code, exc.message),
        )

    return app


app = create_app()
