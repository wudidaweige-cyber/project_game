"""SQL guard: only safe SELECT may pass."""

import pytest

from app.mcp.sql_guard import SqlGuardError, validate_readonly_sql


def test_accepts_simple_select():
    sql = validate_readonly_sql("SELECT id, name FROM ops_game WHERE status = 1")
    assert sql.upper().startswith("SELECT")


def test_rejects_insert():
    with pytest.raises(SqlGuardError):
        validate_readonly_sql("INSERT INTO ops_game (id) VALUES ('x')")


def test_rejects_drop_and_multi_statement():
    with pytest.raises(SqlGuardError):
        validate_readonly_sql("SELECT 1; DROP TABLE ops_game")
    with pytest.raises(SqlGuardError):
        validate_readonly_sql("DELETE FROM ops_order")


def test_rejects_update_and_forbidden_tables_optional():
    with pytest.raises(SqlGuardError):
        validate_readonly_sql("UPDATE ops_order SET price = 0")
