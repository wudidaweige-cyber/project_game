"""Knowledge Q&A agent tests with mocked retriever + LLM."""

from app.agent.knowledge import answer_knowledge_question


class _FakeLLM:
    def __init__(self, answer: str):
        self.answer = answer
        self.calls = []

    def chat(self, messages, temperature=0.0):
        self.calls.append(messages)
        return self.answer


def test_knowledge_agent_answers_with_citations(monkeypatch):
    monkeypatch.setattr(
        "app.agent.knowledge.search_knowledge",
        lambda query, top_k=5, doc_type=None: {
            "ok": True,
            "hits": [
                {
                    "chunk_id": "c1",
                    "doc_id": "d1",
                    "doc_type": "refund",
                    "title": "退款规则",
                    "source_path": "rule-refund.md",
                    "chunk_index": 0,
                    "score": 0.1,
                    "content": "## 可退款情形\n支付后无法交付可全额退款。",
                }
            ],
        },
    )
    fake = _FakeLLM("根据《退款规则》，支付后账号无法交付可全额退款。[1]")
    monkeypatch.setattr("app.agent.knowledge.get_llm_client", lambda: fake)

    result = answer_knowledge_question("什么情况可以全额退款？")
    assert result["ok"] is True
    assert "退款" in result["answer"]
    assert len(result["citations"]) == 1
    assert result["citations"][0]["title"] == "退款规则"
    assert len(fake.calls) == 1


def test_knowledge_agent_no_hit_does_not_call_llm(monkeypatch):
    monkeypatch.setattr(
        "app.agent.knowledge.search_knowledge",
        lambda query, top_k=5, doc_type=None: {"ok": True, "hits": []},
    )

    called = {"n": 0}

    class _Boom:
        def chat(self, *args, **kwargs):
            called["n"] += 1
            return "不应生成"

    monkeypatch.setattr("app.agent.knowledge.get_llm_client", lambda: _Boom())

    result = answer_knowledge_question("银河系退款政策是什么？")
    assert result["ok"] is True
    assert result["no_hit"] is True
    assert called["n"] == 0
    assert result["citations"] == []
    assert "依据" in result["answer"] or "检索" in result["answer"]
