"""HTTP tests for MCP facade (auth required)."""


def test_mcp_tools_list_and_call(client, auth_headers):
    listed = client.get("/api/v1/mcp/tools", headers=auth_headers).json()
    assert listed["code"] == 200
    names = {t["name"] for t in listed["data"]["tools"]}
    assert "query_gmv" in names

    blocked = client.post(
        "/api/v1/mcp/tools/run_readonly_sql/call",
        headers=auth_headers,
        json={"arguments": {"sql": "DROP TABLE ops_game"}},
    ).json()
    assert blocked["code"] == 501
