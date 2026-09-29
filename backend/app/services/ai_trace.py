"""Persist AI sessions, tasks, and agent execution traces."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import session_scope
from app.models.ai import AiAgentExecution, AiSession, AiTask
from app.models.user import SysUser

_STRING_LITERAL_RE = re.compile(r"'([^']|'')*'")


def truncate(text: str, max_len: int = 4000) -> str:
    raw = text or ""
    if len(raw) <= max_len:
        return raw
    return raw[: max_len - 3] + "..."


def mask_sql(sql: str) -> str:
    """Replace string literals so phones/secrets do not land in traces."""
    return _STRING_LITERAL_RE.sub("'***'", sql or "")


def _session_to_dict(row: AiSession) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "title": row.title,
        "status": row.status,
        "create_time": row.create_time.isoformat() if row.create_time else None,
    }


def _task_to_dict(row: AiTask) -> dict[str, Any]:
    return {
        "id": row.id,
        "session_id": row.session_id,
        "task_type": row.task_type,
        "question": row.question,
        "status": row.status,
        "result_summary": row.result_summary,
        "error_message": row.error_message,
        "create_time": row.create_time.isoformat() if row.create_time else None,
        "update_time": row.update_time.isoformat() if row.update_time else None,
    }


def _execution_to_dict(row: AiAgentExecution) -> dict[str, Any]:
    return {
        "id": row.id,
        "task_id": row.task_id,
        "agent_name": row.agent_name,
        "step_no": row.step_no,
        "tool_name": row.tool_name,
        "input_summary": row.input_summary,
        "output_summary": row.output_summary,
        "sql_text_masked": row.sql_text_masked,
        "latency_ms": row.latency_ms,
        "status": row.status,
        "create_time": row.create_time.isoformat() if row.create_time else None,
    }


def ensure_demo_user(db) -> str:
    """Keep Phase A helper; prefer auth_users.ensure_demo_users for passwords."""
    from app.services.auth_users import OPERATOR_ID, ensure_demo_users

    ensure_demo_users()
    settings = get_settings()
    existing = db.get(SysUser, settings.demo_user_id)
    if existing:
        return existing.id
    return OPERATOR_ID


def create_session(*, title: str = "", user_id: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    with session_scope() as db:
        if user_id:
            user = db.get(SysUser, user_id)
            if not user:
                raise ValueError("user not found")
            uid = user.id
            uname = user.display_name or user.username
        else:
            uid = ensure_demo_user(db)
            uname = settings.demo_display_name
        row = AiSession(
            id=str(uuid.uuid4()),
            user_id=uid,
            title=(title or "").strip()[:256],
            status="active",
            create_user_id=uid,
            create_user_name=uname,
            update_user_id=uid,
            update_user_name=uname,
        )
        db.add(row)
        db.flush()
        return _session_to_dict(row)


def list_sessions(*, limit: int = 20) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 100))
    with session_scope() as db:
        rows = db.scalars(
            select(AiSession).order_by(AiSession.create_time.desc()).limit(lim)
        ).all()
        return [_session_to_dict(r) for r in rows]


def get_session(session_id: str) -> dict[str, Any] | None:
    with session_scope() as db:
        row = db.get(AiSession, session_id)
        return _session_to_dict(row) if row else None


def create_task(
    *,
    session_id: str,
    question: str,
    task_type: str = "mixed",
) -> dict[str, Any]:
    settings = get_settings()
    q = (question or "").strip()
    if not q:
        raise ValueError("question is empty")
    with session_scope() as db:
        session = db.get(AiSession, session_id)
        if not session:
            raise ValueError("session not found")
        uid = session.user_id
        row = AiTask(
            id=str(uuid.uuid4()),
            session_id=session_id,
            task_type=task_type or "mixed",
            question=truncate(q, 2000),
            status="pending",
            result_summary="",
            error_message="",
            create_user_id=uid,
            create_user_name=settings.demo_display_name,
            update_user_id=uid,
            update_user_name=settings.demo_display_name,
        )
        db.add(row)
        db.flush()
        return _task_to_dict(row)


def mark_task_running(task_id: str) -> dict[str, Any]:
    with session_scope() as db:
        row = db.get(AiTask, task_id)
        if not row:
            raise ValueError("task not found")
        row.status = "running"
        db.flush()
        return _task_to_dict(row)


def append_execution(
    *,
    task_id: str,
    agent_name: str,
    step_no: int,
    tool_name: str = "",
    input_summary: str = "",
    output_summary: str = "",
    sql_text: str = "",
    latency_ms: int = 0,
    status: str = "success",
) -> dict[str, Any]:
    settings = get_settings()
    with session_scope() as db:
        task = db.get(AiTask, task_id)
        if not task:
            raise ValueError("task not found")
        row = AiAgentExecution(
            id=str(uuid.uuid4()),
            task_id=task_id,
            agent_name=agent_name,
            step_no=int(step_no),
            tool_name=tool_name or "",
            input_summary=truncate(input_summary),
            output_summary=truncate(output_summary),
            sql_text_masked=truncate(mask_sql(sql_text)),
            latency_ms=max(0, int(latency_ms)),
            status=status or "success",
            create_user_id=task.create_user_id,
            create_user_name=settings.demo_display_name,
            update_user_id=task.update_user_id,
            update_user_name=settings.demo_display_name,
        )
        db.add(row)
        db.flush()
        return _execution_to_dict(row)


def finish_task(
    *,
    task_id: str,
    status: str,
    result_summary: str = "",
    error_message: str = "",
) -> dict[str, Any]:
    with session_scope() as db:
        row = db.get(AiTask, task_id)
        if not row:
            raise ValueError("task not found")
        row.status = status
        row.result_summary = truncate(result_summary)
        row.error_message = truncate(error_message)
        db.flush()
        return _task_to_dict(row)


def update_task_type(task_id: str, task_type: str) -> dict[str, Any]:
    with session_scope() as db:
        row = db.get(AiTask, task_id)
        if not row:
            raise ValueError("task not found")
        row.task_type = task_type or row.task_type
        db.flush()
        return _task_to_dict(row)


def get_task(task_id: str) -> dict[str, Any] | None:
    with session_scope() as db:
        row = db.get(AiTask, task_id)
        return _task_to_dict(row) if row else None


def list_executions(task_id: str) -> list[dict[str, Any]]:
    with session_scope() as db:
        rows = db.scalars(
            select(AiAgentExecution)
            .where(AiAgentExecution.task_id == task_id)
            .order_by(AiAgentExecution.step_no.asc(), AiAgentExecution.create_time.asc())
        ).all()
        return [_execution_to_dict(r) for r in rows]
