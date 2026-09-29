"""Supervisor routing tests with mocked LLM + agents."""



from app.agent.supervisor import build_supervisor_graph, run_supervisor





class _FakeLLM:

    def __init__(self, responses: list[str]):

        self.responses = list(responses)

        self.calls = []



    def chat(self, messages, temperature=0.0):

        self.calls.append(messages)

        if not self.responses:

            return "{}"

        return self.responses.pop(0)





def test_supervisor_routes_to_data(monkeypatch):

    fake = _FakeLLM(['{"route":"data","reason":"查GMV"}'])

    monkeypatch.setattr("app.agent.supervisor.get_llm_client", lambda: fake)

    monkeypatch.setattr(

        "app.agent.supervisor.analyze_question",

        lambda q, max_rows=100: {

            "ok": True,

            "answer": "近7天GMV为1000元",

            "executed_sql": "SELECT 1",

            "sql": "SELECT 1",

            "row_count": 1,

            "rows": [{"gmv": 1000}],

        },

    )

    # reset compiled graph cache so nodes pick up monkeypatch

    monkeypatch.setattr("app.agent.supervisor._GRAPH", None)



    result = run_supervisor("最近7天GMV是多少？")

    assert result["ok"] is True

    assert result["route_decision"] == "data"

    assert "supervisor" in result["route"]

    assert "data_agent" in result["route"]

    assert "knowledge_agent" not in result["route"]

    assert "1000" in result["answer"]

    assert any(r.get("type") == "sql" for r in result["refs"])





def test_supervisor_routes_to_knowledge(monkeypatch):

    fake = _FakeLLM(['{"route":"knowledge","reason":"退款规则"}'])

    monkeypatch.setattr("app.agent.supervisor.get_llm_client", lambda: fake)

    monkeypatch.setattr(

        "app.agent.supervisor.answer_knowledge_question",

        lambda q, top_k=5, doc_type=None: {

            "ok": True,

            "answer": "无法交付可全额退款。[1]",

            "citations": [

                {

                    "index": 1,

                    "title": "退款规则",

                    "doc_type": "refund",

                    "source_path": "rule-refund.md",

                    "score": 0.1,

                    "snippet": "无法交付",

                }

            ],

            "no_hit": False,

            "hit_count": 1,

        },

    )

    monkeypatch.setattr("app.agent.supervisor._GRAPH", None)



    result = run_supervisor("什么情况下可以全额退款？")

    assert result["ok"] is True

    assert result["route_decision"] == "knowledge"

    assert "knowledge_agent" in result["route"]

    assert "data_agent" not in result["route"]

    assert "退款" in result["answer"]

    assert any(r.get("type") == "knowledge" for r in result["refs"])





def test_supervisor_both_then_synthesize(monkeypatch):

    fake = _FakeLLM(

        [

            '{"route":"both","reason":"异常+规则"}',

            "出租率下降，按退款规则应先核验订单再处理。[1]",

        ]

    )

    monkeypatch.setattr("app.agent.supervisor.get_llm_client", lambda: fake)

    monkeypatch.setattr(

        "app.agent.supervisor.analyze_question",

        lambda q, max_rows=100: {

            "ok": True,

            "answer": "出租率环比下降12%",

            "executed_sql": "SELECT rent_rate",

            "sql": "SELECT rent_rate",

            "row_count": 1,

            "rows": [],

        },

    )

    monkeypatch.setattr(

        "app.agent.supervisor.answer_knowledge_question",

        lambda q, top_k=5, doc_type=None: {

            "ok": True,

            "answer": "异常订单按 SOP 升级处理。[1]",

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

    assert result["route_decision"] == "both"

    assert result["route"] == ["supervisor", "data_agent", "knowledge_agent"]

    assert "出租率" in result["answer"] or "退款" in result["answer"] or "SOP" in result["answer"]

    assert len(fake.calls) == 2  # classify + synthesize





def test_supervisor_rejects_write_intent(monkeypatch):

    fake = _FakeLLM(['{"route":"reject","reason":"写库"}'])

    monkeypatch.setattr("app.agent.supervisor.get_llm_client", lambda: fake)

    called = {"data": 0, "knowledge": 0}



    def _data(*args, **kwargs):

        called["data"] += 1

        return {"ok": True, "answer": "no"}



    def _knowledge(*args, **kwargs):

        called["knowledge"] += 1

        return {"ok": True, "answer": "no"}



    monkeypatch.setattr("app.agent.supervisor.analyze_question", _data)

    monkeypatch.setattr("app.agent.supervisor.answer_knowledge_question", _knowledge)

    monkeypatch.setattr("app.agent.supervisor._GRAPH", None)



    result = run_supervisor("把所有订单金额改成0")

    assert result["ok"] is False

    assert "拒绝" in result["error"]

    assert called["data"] == 0

    assert called["knowledge"] == 0

    assert "reject" in result["route"]





def test_build_graph_compiles():

    g = build_supervisor_graph()

    assert g is not None

