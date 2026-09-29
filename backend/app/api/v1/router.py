from fastapi import APIRouter, Depends

from app.api.v1 import agent_api, auth_api, dashboard, health, knowledge_api, mcp_api
from app.core.deps import get_current_user

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth_api.router)
api_router.include_router(dashboard.router, dependencies=[Depends(get_current_user)])
api_router.include_router(mcp_api.router, dependencies=[Depends(get_current_user)])
api_router.include_router(agent_api.router, dependencies=[Depends(get_current_user)])
api_router.include_router(knowledge_api.router, dependencies=[Depends(get_current_user)])
