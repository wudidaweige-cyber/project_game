"""NL2SQL agent tests with mocked LLM (no live model required)."""

from app.agent.nl2sql import analyze_question


class _FakeLLM:
    def __init__(self, sql: str, answer: str):
        self.sql = sql
        self.answer = answer
        self.calls = []

    def chat(self, messages, temperature=0.0):
        self.calls.append(messages)
        # first call = SQL generation; second = answer
        if len(self.calls) == 1:
            return self.sql
        return self.answer


def test_nl2sql_happy_path(monkeypatch):
    fake = _FakeLLM(
        sql="SELECT name FROM ops_game ORDER BY name LIMIT 5",
        answer="当前库中有多款游戏，例如王者荣耀等。",
    )
    monkeypatch.setattr("app.agent.nl2sql.get_llm_client", lambda: fake)

    result = analyze_question("有哪些游戏？")
    assert result["ok"] is True
    assert result["sql"]
    assert "SELECT" in result["sql"].upper()
    assert result["answer"]
    assert result["row_count"] >= 0


def test_nl2sql_blocks_write_sql(monkeypatch):
    fake = _FakeLLM(
        sql="DELETE FROM ops_game",
        answer="should not reach",
    )
    monkeypatch.setattr("app.agent.nl2sql.get_llm_client", lambda: fake)

    result = analyze_question("删掉所有游戏")
    assert result["ok"] is False
    assert result["sql"] == "" or "DELETE" not in (result.get("executed_sql") or "")
    assert "拒绝" in result["error"] or "SELECT" in result["error"]
