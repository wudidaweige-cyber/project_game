"""Tests for AI session/task persistence service."""

from app.services import ai_trace


def test_mask_sql_redacts_string_literals():
    raw = "SELECT * FROM ops_order WHERE buyer_phone = '13800138000'"
    masked = ai_trace.mask_sql(raw)
    assert "13800138000" not in masked
    assert "***" in masked


def test_create_session_and_task_roundtrip():
    session = ai_trace.create_session(title="测试会话")
    assert session["id"]
    assert session["user_id"]
    task = ai_trace.create_task(
        session_id=session["id"],
        question="最近7天GMV？",
        task_type="data_query",
    )
    assert task["status"] == "pending"
    ai_trace.append_execution(
        task_id=task["id"],
        agent_name="data_agent",
        step_no=1,
        tool_name="run_readonly_sql",
        sql_text="SELECT sum(gmv) FROM ops_daily_metric WHERE x='secret'",
        output_summary="row_count=1",
    )
    ai_trace.finish_task(task_id=task["id"], status="success", result_summary="GMV=100")
    got = ai_trace.get_task(task["id"])
    assert got is not None
    assert got["status"] == "success"
    assert got["result_summary"] == "GMV=100"
    exs = ai_trace.list_executions(task["id"])
    assert len(exs) == 1
    assert "secret" not in exs[0]["sql_text_masked"]


def test_create_task_unknown_session_raises():
    try:
        ai_trace.create_task(session_id="missing-session-id", question="x")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "session not found" in str(exc)
