"""HTTP facade for MCP tools (dev / agent integration without stdio)."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.response import fail, ok
from app.mcp.registry import call_tool, list_tools

router = APIRouter(prefix="/mcp", tags=["mcp"])


class ToolCallRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/tools")
def get_tools() -> dict:
    return ok({"tools": list_tools()})


@router.post("/tools/{name}/call")
def post_tool_call(name: str, body: ToolCallRequest) -> dict:
    result = call_tool(name, body.arguments)
    if not result.get("ok"):
        return fail(501, result.get("error") or "tool failed", result.get("data"))
    return ok(result.get("data"))
