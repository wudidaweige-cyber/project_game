"""In-process agent job queue tests."""

from app.queue.jobs import enqueue_job, ping_queue, process_job, queue_backend


def test_queue_backend_defaults_to_memory(monkeypatch):
    monkeypatch.setattr(
        "app.queue.jobs.get_settings",
        lambda: type("S", (), {"redis_url": ""})(),
    )
    assert queue_backend() == "memory"
    info = ping_queue()
    assert info["ok"] is True
    assert info["backend"] == "memory"


def test_queue_backend_rejects_http_milvus_url(monkeypatch):
    monkeypatch.setattr(
        "app.queue.jobs.get_settings",
        lambda: type("S", (), {"redis_url": "http://192.168.142.130:19530"})(),
    )
    assert queue_backend() == "memory"


def test_process_job_persists_on_existing_task(monkeypatch):
    calls = {}

    monkeypatch.setattr(
        "app.services.ai_trace.mark_task_running",
        lambda task_id: calls.setdefault("running", task_id),
    )
    monkeypatch.setattr(
        "app.agent.supervisor.run_supervisor",
        lambda q, max_rows=100, top_k=5: {
            "ok": True,
            "answer": "ok",
            "question": q,
            "route_decision": "data",
            "route": ["supervisor", "data_agent"],
            "route_reason": "",
            "refs": [],
            "data": {"ok": True, "row_count": 1, "sql": "SELECT 1", "executed_sql": "SELECT 1"},
            "knowledge": {},
            "anomaly": {},
            "strategy": {},
            "error": "",
        },
    )
    monkeypatch.setattr(
        "app.api.v1.agent_api.persist_supervisor_result",
        lambda **kwargs: calls.__setitem__("persist", kwargs)
        or {"task_id": kwargs["task_id"], "ok": True},
    )

    job = {
        "task_id": "t1",
        "session_id": "s1",
        "question": "有哪些游戏？",
        "max_rows": 10,
        "top_k": 5,
    }
    out = process_job(job)
    assert calls["running"] == "t1"
    assert calls["persist"]["task_id"] == "t1"
    assert out["task_id"] == "t1"


def test_enqueue_memory_then_dequeue(monkeypatch):
    monkeypatch.setattr(
        "app.queue.jobs.get_settings",
        lambda: type("S", (), {"redis_url": ""})(),
    )
    from app.queue import jobs as jq

    # drain
    while True:
        job = jq.dequeue_job(timeout=0.01)
        if not job:
            break
    enqueue_job({"task_id": "abc", "session_id": "s", "question": "q"})
    got = jq.dequeue_job(timeout=1)
    assert got["task_id"] == "abc"
