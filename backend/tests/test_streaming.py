"""Streaming helpers / extract_sql regression tests."""

from app.agent.nl2sql import extract_sql
from app.agent.sse import sse_encode


def test_extract_sql_prefers_with_over_inner_select():
    raw = """说明如下：
WITH recent AS (
  SELECT metric_date, rent_rate FROM ops_game_daily_metric
)
SELECT * FROM recent"""
    sql = extract_sql(raw)
    assert sql.upper().startswith("WITH")
    assert "ops_game_daily_metric" in sql


def test_sse_encode_format():
    line = sse_encode("token", {"text": "你好"})
    assert line.startswith("event: token\n")
    assert '"text": "你好"' in line
    assert line.endswith("\n\n")
