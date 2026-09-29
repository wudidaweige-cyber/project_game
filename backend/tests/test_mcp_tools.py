"""MCP business tools smoke tests (need seeded DB)."""

from datetime import date, timedelta

from app.mcp.registry import call_tool, list_tools


def test_list_tools_includes_core_names():
    names = {t["name"] for t in list_tools()}
    assert "list_games" in names
    assert "query_gmv" in names
    assert "query_rent_rate" in names
    assert "query_orders_summary" in names
    assert "run_readonly_sql" in names


def test_list_games_and_metrics_tools():
    games = call_tool("list_games", {"limit": 10})
    assert games["ok"] is True
    assert len(games["data"]) >= 1
    assert "name" in games["data"][0]

    end = date.today()
    start = end - timedelta(days=7)
    gmv = call_tool(
        "query_gmv",
        {"start_date": start.isoformat(), "end_date": end.isoformat()},
    )
    assert gmv["ok"] is True
    assert "gmv" in gmv["data"]

    rent = call_tool(
        "query_rent_rate",
        {"start_date": start.isoformat(), "end_date": end.isoformat()},
    )
    assert rent["ok"] is True
    assert "rent_rate" in rent["data"]

    orders = call_tool(
        "query_orders_summary",
        {"start_date": start.isoformat(), "end_date": end.isoformat(), "limit": 5},
    )
    assert orders["ok"] is True
    assert "order_count" in orders["data"]


def test_run_readonly_sql_blocks_write():
    result = call_tool("run_readonly_sql", {"sql": "DELETE FROM ops_game"})
    assert result["ok"] is False
    assert "SELECT" in result["error"] or "拒绝" in result["error"] or "forbidden" in result["error"].lower()
