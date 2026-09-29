"""Stream persistence wrapper tests (no live LLM)."""

from app.api.v1.agent_api import iter_traced_supervisor_stream
from app.services import ai_trace


def test_stream_wrapper_persists_on_done(monkeypatch):
    def fake_stream(question, max_rows=100, top_k=5):
        yield {"event": "meta", "phase": "start", "question": question}
        yield {
            "event": "meta",
            "phase": "routed",
            "route_decision": "knowledge",
            "route_reason": "t",
            "route": ["supervisor", "knowledge_agent"],
        }
        yield {"event": "token", "text": "可全额退款"}
        yield {
            "event": "done",
            "answer": "可全额退款",
            "route": ["supervisor", "knowledge_agent"],
            "route_decision": "knowledge",
            "refs": [],
            "sql": "",
            "row_count": 0,
            "citations": [{"index": 1, "title": "退款"}],
            "no_hit": False,
        }

    monkeypatch.setattr("app.api.v1.agent_api.run_supervisor_stream", fake_stream)
    session = ai_trace.create_session(title="stream")
    events = list(iter_traced_supervisor_stream(session["id"], "什么情况全额退款？"))
    assert any(e.get("event") == "done" for e in events)
    task_id = next(e["task_id"] for e in events if e.get("task_id"))
    task = ai_trace.get_task(task_id)
    assert task is not None
    assert task["status"] == "success"
    assert "退款" in task["result_summary"]
    exs = ai_trace.list_executions(task_id)
    names = [e["agent_name"] for e in exs]
    assert "supervisor" in names
    assert "knowledge_agent" in names


def test_stream_wrapper_persists_on_error(monkeypatch):
    def fake_stream(question, max_rows=100, top_k=5):
        yield {"event": "meta", "phase": "start", "question": question}
        yield {
            "event": "meta",
            "phase": "routed",
            "route_decision": "data",
            "route_reason": "t",
            "route": ["supervisor", "data_agent"],
        }
        yield {"event": "error", "error": "查询执行失败"}

    monkeypatch.setattr("app.api.v1.agent_api.run_supervisor_stream", fake_stream)
    session = ai_trace.create_session(title="stream-err")
    events = list(iter_traced_supervisor_stream(session["id"], "GMV?"))
    assert any(e.get("event") == "error" for e in events)
    task_id = next(e["task_id"] for e in events if e.get("task_id"))
    task = ai_trace.get_task(task_id)
    assert task["status"] == "failed"
    assert "失败" in task["error_message"]
