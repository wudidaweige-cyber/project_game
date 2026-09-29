"""Create tables then assert ops_game exists (integration-ish)."""

from sqlalchemy import inspect, text


def test_create_all_tables_and_insert_game():
    from app.core.db import get_engine
    from app.models import Base
    import uuid
    from datetime import datetime, timezone

    engine = get_engine()
    # 仅确保表存在，避免 drop_all 清空开发库演示数据
    Base.metadata.create_all(bind=engine)

    names = set(inspect(engine).get_table_names())
    assert "ops_game" in names
    assert "ops_order" in names
    assert "sys_user" in names
    assert "ai_task" in names

    now = datetime.now(timezone.utc)
    game_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ops_game (
                  id, name, category, platform, status,
                  create_user_id, create_user_name,
                  update_user_id, update_user_name,
                  create_time, update_time
                ) VALUES (
                  :id, :name, :category, :platform, :status,
                  :cuid, :cuname, :uuid, :uname, :ctime, :utime
                )
                """
            ),
            {
                "id": game_id,
                "name": "测试游戏",
                "category": "MOBA",
                "platform": "PC",
                "status": 1,
                "cuid": "system",
                "cuname": "system",
                "uuid": "system",
                "uname": "system",
                "ctime": now,
                "utime": now,
            },
        )
        row = conn.execute(
            text("SELECT name FROM ops_game WHERE id = :id"),
            {"id": game_id},
        ).fetchone()
        conn.execute(text("DELETE FROM ops_game WHERE id = :id"), {"id": game_id})
    assert row is not None
    assert row[0] == "测试游戏"
