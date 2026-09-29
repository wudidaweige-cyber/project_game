"""API tests for agent sessions / ask persistence (auth required)."""


def test_create_and_get_session(client, auth_headers):
    r = client.post(
        "/api/v1/agent/sessions",
        headers=auth_headers,
        json={"title": "单元测试会话"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 200
    sid = body["data"]["id"]
    r2 = client.get(f"/api/v1/agent/sessions/{sid}", headers=auth_headers)
    assert r2.json()["data"]["id"] == sid


def test_session_ask_persists_task(client, auth_headers, monkeypatch):
    from app.api.v1 import agent_api

    monkeypatch.setattr(
        agent_api,
        "run_supervisor",
        lambda q, max_rows=100, top_k=5: {
            "ok": True,
            "task_id": "ignored",
            "question": q,
            "answer": "GMV=1",
            "route": ["supervisor", "data_agent"],
            "route_decision": "data",
            "route_reason": "test",
            "refs": [{"type": "sql", "summary": "SELECT 1"}],
            "data": {
                "ok": True,
                "executed_sql": "SELECT 1",
                "sql": "SELECT 1",
                "row_count": 1,
            },
            "knowledge": None,
            "error": "",
        },
    )
    sid = client.post(
        "/api/v1/agent/sessions",
        headers=auth_headers,
        json={"title": "ask"},
    ).json()["data"]["id"]
    r = client.post(
        f"/api/v1/agent/sessions/{sid}/ask",
        headers=auth_headers,
        json={"question": "最近7天GMV?"},
    )
    assert r.json()["code"] == 200
    tid = r.json()["data"]["task_id"]
    task = client.get(f"/api/v1/agent/tasks/{tid}", headers=auth_headers).json()["data"]
    assert task["status"] == "success"
    assert "GMV" in task["result_summary"]
    exs = client.get(
        f"/api/v1/agent/tasks/{tid}/executions",
        headers=auth_headers,
    ).json()["data"]
    assert any(e["agent_name"] == "supervisor" for e in exs)
    assert any(e["agent_name"] == "data_agent" for e in exs)


def test_session_ask_failed_still_persists(client, auth_headers, monkeypatch):
    from app.api.v1 import agent_api

    monkeypatch.setattr(
        agent_api,
        "run_supervisor",
        lambda q, max_rows=100, top_k=5: {
            "ok": False,
            "task_id": "x",
            "question": q,
            "answer": "",
            "route": ["supervisor", "reject"],
            "route_decision": "reject",
            "route_reason": "写库",
            "refs": [],
            "data": None,
            "knowledge": None,
            "error": "安全策略拒绝：不允许写库",
        },
    )
    sid = client.post(
        "/api/v1/agent/sessions",
        headers=auth_headers,
        json={},
    ).json()["data"]["id"]
    r = client.post(
        f"/api/v1/agent/sessions/{sid}/ask",
        headers=auth_headers,
        json={"question": "把订单改成0"},
    )
    assert r.json()["code"] == 501
    tid = r.json()["data"]["task_id"]
    task = client.get(f"/api/v1/agent/tasks/{tid}", headers=auth_headers).json()["data"]
    assert task["status"] == "failed"
    assert "拒绝" in task["error_message"]


def test_ask_unknown_session_404(client, auth_headers):
    r = client.post(
        "/api/v1/agent/sessions/not-exist/ask",
        headers=auth_headers,
        json={"question": "hello"},
    )
    assert r.json()["code"] == 404
