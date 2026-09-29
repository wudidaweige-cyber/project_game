"""NL2SQL extract / repair / retry stability tests."""

from app.agent.nl2sql import analyze_question, extract_sql, repair_sql, check_sql_structure


def test_extract_sql_prefers_with_when_both_present():
    text = """说明：
```sql
SELECT 1;
WITH recent AS (
  SELECT SUM(gmv) AS gmv FROM ops_daily_metric WHERE game_id = ''
)
SELECT gmv FROM recent
```
"""
    sql = extract_sql(text)
    assert sql.upper().startswith("WITH")
    assert "FROM recent" in sql


def test_repair_sql_prepends_with_for_bare_cte():
    bare = (
        "recent AS (SELECT SUM(gmv) AS gmv FROM ops_daily_metric WHERE game_id = ''), "
        "baseline AS (SELECT SUM(gmv) AS gmv FROM ops_daily_metric WHERE game_id = '') "
        "SELECT r.gmv FROM recent r"
    )
    fixed = repair_sql(bare)
    assert fixed.upper().startswith("WITH ")
    assert check_sql_structure(fixed) is None


def test_check_sql_structure_rejects_unbalanced_parens():
    err = check_sql_structure("SELECT (1 FROM ops_game")
    assert err is not None
    assert "括号" in err or "paren" in err.lower()


def test_nl2sql_retries_once_after_bad_sql(monkeypatch):
    responses = [
        "recent AS (SELECT 1 AS x) SELECT x FROM recent",  # missing WITH → repair may fix
        # Force a case that needs LLM retry: invalid after repair still fails guard
    ]
    # Use DELETE first (guard fail), then valid SELECT
    responses = [
        "DELETE FROM ops_game",
        "SELECT name FROM ops_game ORDER BY name LIMIT 5",
        "库中有游戏列表。",
    ]

    class _Fake:
        def __init__(self):
            self.calls = []

        def chat(self, messages, temperature=0.0):
            self.calls.append(messages)
            return responses.pop(0)

    fake = _Fake()
    monkeypatch.setattr("app.agent.nl2sql.get_llm_client", lambda: fake)

    result = analyze_question("有哪些游戏？")
    assert result["ok"] is True
    assert "SELECT" in (result.get("executed_sql") or "").upper()
    assert result.get("sql_attempts", 1) >= 2
    assert len(fake.calls) >= 2  # generate + retry (+ maybe summarize)
