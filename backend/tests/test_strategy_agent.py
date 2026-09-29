"""Strategy analysis agent + supervisor routing tests."""

from app.agent.strategy import analyze_strategy
from app.agent.supervisor import _parse_route, run_supervisor


def test_parse_route_strategy_heuristic():
    decision, _ = _parse_route("{}", question="根据最近指标给出运营策略建议")
    assert decision == "strategy"


def test_parse_route_strategy_knowledge_heuristic():
    decision, _ = _parse_route(
        "{}",
        question="按定价规则给出调价建议",
    )
    assert decision == "strategy_knowledge"


def test_parse_route_write_intent_still_reject():
    decision, _ = _parse_route("{}", question="请直接改价落库执行 UPDATE")
    assert decision == "reject"


def test_analyze_strategy_rejects_write_intent():
    result = analyze_strategy("请直接修改价格并执行写库")
    assert result["ok"] is False
    assert "写库" in (result.get("error") or "") or "拒绝" in (result.get("error") or "")


def test_supervisor_routes_to_strategy(monkeypatch):
    fake_responses = ['{"route":"strategy","reason":"策略建议"}']

    class _Fake:
        def chat(self, messages, temperature=0.0):
            return fake_responses.pop(0)

    monkeypatch.setattr("app.agent.supervisor.get_llm_client", lambda: _Fake())
    monkeypatch.setattr(
        "app.agent.supervisor.analyze_strategy",
        lambda q, with_knowledge=False, top_k=5: {
            "ok": True,
            "answer": "建议观察调价，系统不会自动修改业务数据。",
            "snapshot": {"platform_alerts": [{"metric": "gmv"}]},
            "knowledge": None,
            "refs": [{"type": "strategy_snapshot", "summary": "ok", "alerts": []}],
            "suggestions_only": True,
            "error": "",
        },
    )
    monkeypatch.setattr("app.agent.supervisor._GRAPH", None)

    result = run_supervisor("根据最近指标给出运营策略建议")
    assert result["ok"] is True
    assert result["route_decision"] == "strategy"
    assert "strategy_agent" in result["route"]
    assert "data_agent" not in result["route"]
    assert result["strategy"] is not None
    assert "不会自动修改业务数据" in result["answer"]


def test_supervisor_strategy_with_knowledge(monkeypatch):
    fake_responses = ['{"route":"strategy_knowledge","reason":"策略+规则"}']

    class _Fake:
        def chat(self, messages, temperature=0.0):
            return fake_responses.pop(0)

    monkeypatch.setattr("app.agent.supervisor.get_llm_client", lambda: _Fake())
    monkeypatch.setattr(
        "app.agent.supervisor.analyze_strategy",
        lambda q, with_knowledge=False, top_k=5: {
            "ok": True,
            "answer": "对照定价规则给出观察调价建议。以上仅为人工决策参考，系统不会自动修改业务数据。",
            "snapshot": {"has_data": True, "platform_alerts": []},
            "knowledge": {
                "ok": True,
                "answer": "定价需人工复核。[1]",
                "citations": [
                    {
                        "index": 1,
                        "title": "定价规则",
                        "doc_type": "pricing",
                        "source_path": "pricing.md",
                        "score": 0.3,
                        "snippet": "人工复核",
                    }
                ],
                "no_hit": False,
                "hit_count": 1,
            },
            "refs": [
                {"type": "strategy_snapshot", "summary": "ok", "alerts": []},
                {"type": "knowledge", "index": 1, "title": "定价规则"},
            ],
            "suggestions_only": True,
            "error": "",
        },
    )
    monkeypatch.setattr("app.agent.supervisor._GRAPH", None)

    result = run_supervisor("按定价规则给出调价建议")
    assert result["ok"] is True
    assert result["route_decision"] == "strategy_knowledge"
    assert result["route"] == ["supervisor", "strategy_agent", "knowledge_agent"]
    assert result["knowledge"] is not None
