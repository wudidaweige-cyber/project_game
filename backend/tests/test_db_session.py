from sqlalchemy import text

from app.core.db import session_scope


def test_session_scope_executes_select():
    with session_scope() as db:
        row = db.execute(text("SELECT 1 AS n")).mappings().first()
        assert row["n"] == 1
