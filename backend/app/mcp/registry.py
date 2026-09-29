"""MCP tool registry — name, schema, handler."""

from __future__ import annotations

from typing import Any, Callable

from app.mcp import tools_impl

ToolHandler = Callable[..., dict[str, Any]]

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "list_games",
        "description": "列出游戏主数据（id/名称/分类/平台/状态），只读。",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 50, "description": "返回条数，最大200"},
                "status": {"type": "integer", "description": "状态过滤，默认1；不传则不过滤"},
            },
        },
        "handler": tools_impl.list_games,
    },
    {
        "name": "query_gmv",
        "description": "按日期区间查询 GMV 与订单量（默认全站日指标汇总）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "game_id": {"type": "string", "description": "可选，指定游戏"},
            },
            "required": ["start_date", "end_date"],
        },
        "handler": tools_impl.query_gmv,
    },
    {
        "name": "query_rent_rate",
        "description": "按日期区间查询出租率/退款率均值（默认全站）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "game_id": {"type": "string"},
            },
            "required": ["start_date", "end_date"],
        },
        "handler": tools_impl.query_rent_rate,
    },
    {
        "name": "query_orders_summary",
        "description": "按日期区间汇总订单量/GMV，并返回最近若干条订单样例。",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "game_id": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["start_date", "end_date"],
        },
        "handler": tools_impl.query_orders_summary,
    },
    {
        "name": "query_game_metric_rank",
        "description": "按指标对游戏排行：gmv / order_count / rent_rate / refund_rate。",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["metric", "start_date", "end_date"],
        },
        "handler": tools_impl.query_game_metric_rank,
    },
    {
        "name": "run_readonly_sql",
        "description": "执行只读 SQL（仅 SELECT/WITH）。写操作与危险关键字一律拒绝。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string"},
                "max_rows": {"type": "integer", "default": 100},
            },
            "required": ["sql"],
        },
        "handler": tools_impl.run_readonly_sql,
    },
]

_HANDLERS: dict[str, ToolHandler] = {t["name"]: t["handler"] for t in TOOL_SPECS}


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["input_schema"],
        }
        for t in TOOL_SPECS
    ]


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"ok": False, "data": None, "error": f"未知工具: {name}"}
    args = arguments or {}
    try:
        return handler(**args)
    except TypeError as exc:
        return {"ok": False, "data": None, "error": f"参数错误: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "data": None, "error": f"工具执行失败: {exc}"}
