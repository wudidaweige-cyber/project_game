"""Anomaly detection + agent routing tests."""

from datetime import date, timedelta

from app.agent.supervisor import _parse_route, run_supervisor
from app.services.anomaly import detect_metric_anomalies


def test_parse_route_anomaly_heuristic():
    decision, _ = _parse_route("{}", question="最近出租率为何异常？")
    assert decision == "anomaly"


def test_parse_route_anomaly_knowledge_heuristic():
    decision, _ = _parse_route(
        "{}",
        question="最近出租率为何异常？按退款规则该怎么处理？",
    )
    assert decision == "anomaly_knowledge"


def test_detect_metric_anomalies_runs():
    end = date.today()
    report = detect_metric_anomalies(window_days=7, end_date=end)
    assert report["ok"] is True
    assert "recent" in report
    assert "baseline" in report
    assert isinstance(report.get("platform_alerts"), list)


def test_supervisor_routes_to_anomaly(monkeypatch):
    fake_responses = ['{"route":"anomaly","reason":"异常归因"}']

    class _Fake:
        def chat(self, messages, temperature=0.0):
            return fake_responses.pop(0)

    monkeypatch.setattr("app.agent.supervisor.get_llm_client", lambda: _Fake())
    monkeypatch.setattr(
        "app.agent.supervisor.analyze_anomaly",
        lambda q: {
            "ok": True,
            "answer": "出租率相对基期下降超过阈值，主因游戏A。",
            "findings": {"platform_alerts": [{"metric": "rent_rate"}]},
            "refs": [{"type": "anomaly", "summary": "rent_rate down", "alerts": []}],
            "error": "",
        },
    )
    monkeypatch.setattr("app.agent.supervisor._GRAPH", None)

    result = run_supervisor("最近出租率为何异常？")
    assert result["ok"] is True
    assert result["route_decision"] == "anomaly"
    assert "anomaly_agent" in result["route"]
    assert "data_agent" not in result["route"]
    assert "出租率" in result["answer"] or "下降" in result["answer"]


def test_supervisor_anomaly_then_knowledge(monkeypatch):
    responses = [
        '{"route":"anomaly_knowledge","reason":"异常+规则"}',
        "出租率异常，建议按退款SOP先核验订单再处理。[1]",
    ]

    class _Fake:
        def chat(self, messages, temperature=0.0):
            return responses.pop(0)

    monkeypatch.setattr("app.agent.supervisor.get_llm_client", lambda: _Fake())
    monkeypatch.setattr(
        "app.agent.supervisor.analyze_anomaly",
        lambda q: {
            "ok": True,
            "answer": "出租率环比下降。",
            "findings": {"platform_alerts": [{"metric": "rent_rate"}]},
            "refs": [{"type": "anomaly", "summary": "x", "alerts": []}],
            "error": "",
        },
    )
    monkeypatch.setattr(
        "app.agent.supervisor.answer_knowledge_question",
        lambda q, top_k=5, doc_type=None: {
            "ok": True,
            "answer": "异常订单按 SOP 升级。[1]",
            "citations": [
                {
                    "index": 1,
                    "title": "异常订单SOP",
                    "doc_type": "sop",
                    "source_path": "sop.md",
                    "score": 0.2,
                    "snippet": "升级",
                }
            ],
            "no_hit": False,
            "hit_count": 1,
        },
    )
    monkeypatch.setattr("app.agent.supervisor._GRAPH", None)

    result = run_supervisor("最近出租率为何异常？按退款规则该怎么处理？")
    assert result["ok"] is True
    assert result["route_decision"] == "anomaly_knowledge"
    assert result["route"] == ["supervisor", "anomaly_agent", "knowledge_agent"]
