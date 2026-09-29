"""MCP stdio server entry.

Run (from backend/ with venv):
  python -m app.mcp.server

Exposes readonly business tools via Model Context Protocol (stdio).
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.mcp.registry import call_tool

mcp = FastMCP(
    name="game-ops-readonly",
    instructions="游戏账号租赁运营分析只读工具集。禁止写库。",
)


def _dump(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool(description="列出游戏主数据（id/名称/分类/平台/状态），只读。")
def list_games(limit: int = 50, status: int = 1) -> str:
    return _dump(call_tool("list_games", {"limit": limit, "status": status}))


@mcp.tool(description="按日期区间查询 GMV 与订单量（默认全站日指标汇总）。")
def query_gmv(start_date: str, end_date: str, game_id: str = "") -> str:
    args: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
    if game_id:
        args["game_id"] = game_id
    return _dump(call_tool("query_gmv", args))


@mcp.tool(description="按日期区间查询出租率/退款率均值（默认全站）。")
def query_rent_rate(start_date: str, end_date: str, game_id: str = "") -> str:
    args: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
    if game_id:
        args["game_id"] = game_id
    return _dump(call_tool("query_rent_rate", args))


@mcp.tool(description="按日期区间汇总订单量/GMV，并返回最近若干条订单样例。")
def query_orders_summary(
    start_date: str,
    end_date: str,
    game_id: str = "",
    limit: int = 20,
) -> str:
    args: dict[str, Any] = {
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit,
    }
    if game_id:
        args["game_id"] = game_id
    return _dump(call_tool("query_orders_summary", args))


@mcp.tool(description="按指标对游戏排行：gmv / order_count / rent_rate / refund_rate。")
def query_game_metric_rank(
    metric: str,
    start_date: str,
    end_date: str,
    limit: int = 10,
) -> str:
    return _dump(
        call_tool(
            "query_game_metric_rank",
            {
                "metric": metric,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit,
            },
        )
    )


@mcp.tool(description="执行只读 SQL（仅 SELECT/WITH）。写操作与危险关键字一律拒绝。")
def run_readonly_sql(sql: str, max_rows: int = 100) -> str:
    return _dump(call_tool("run_readonly_sql", {"sql": sql, "max_rows": max_rows}))


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
