"""Agent HTTP API: sessions/tasks + NL2SQL/knowledge/supervisor (JSON + SSE)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agent.anomaly import analyze_anomaly, analyze_anomaly_stream
from app.agent.knowledge import answer_knowledge_question, answer_knowledge_question_stream
from app.agent.nl2sql import analyze_question, analyze_question_stream
from app.agent.sse import sse_response
from app.agent.strategy import analyze_strategy, analyze_strategy_stream
from app.agent.supervisor import run_supervisor, run_supervisor_stream
from app.core.deps import AuthUser, get_current_user
from app.core.response import fail, ok
from app.services import ai_trace

router = APIRouter(prefix="/agent", tags=["agent"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    max_rows: int = Field(100, ge=1, le=200)


class KnowledgeAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(5, ge=1, le=20)
    doc_type: str | None = Field(None, description="可选：sop/refund/account/pricing/risk")


class StrategyAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(5, ge=1, le=20)
    with_knowledge: bool = Field(False, description="是否串联知识库对照规则")


class SupervisorAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    max_rows: int = Field(100, ge=1, le=200)
    top_k: int = Field(5, ge=1, le=20)


class CreateSessionRequest(BaseModel):
    title: str = Field("", max_length=256)


def _map_task_type(route_decision: str) -> str:
    mapping = {
        "data": "data_query",
        "knowledge": "knowledge",
        "both": "mixed",
        "anomaly": "anomaly",
        "anomaly_knowledge": "anomaly",
        "strategy": "strategy",
        "strategy_knowledge": "strategy",
        "reject": "reject",
    }
    return mapping.get(route_decision or "", "mixed")


def _supervisor_response_payload(
    *,
    session_id: str,
    task_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    data_part = result.get("data") or {}
    knowledge_part = result.get("knowledge") or {}
    anomaly_part = result.get("anomaly") or {}
    strategy_part = result.get("strategy") or {}
    return {
        "session_id": session_id,
        "task_id": task_id,
        "question": result.get("question") or "",
        "answer": result.get("answer") or "",
        "route": result.get("route") or [],
        "route_decision": result.get("route_decision") or "",
        "route_reason": result.get("route_reason") or "",
        "refs": result.get("refs") or [],
        "sql": data_part.get("executed_sql") or data_part.get("sql") or "",
        "row_count": data_part.get("row_count", 0),
        "citations": knowledge_part.get("citations")
        or (strategy_part.get("knowledge") or {}).get("citations")
        or [],
        "no_hit": bool(knowledge_part.get("no_hit")),
        "anomaly_alerts": (anomaly_part.get("findings") or {}).get("platform_alerts")
        if isinstance(anomaly_part.get("findings"), dict)
        else [],
        "suggestions_only": bool(strategy_part.get("suggestions_only"))
        if strategy_part
        else False,
        "strategy_snapshot": strategy_part.get("snapshot") or {},
        "error": result.get("error") or "",
    }


def _persist_supervisor_result(
    *,
    session_id: str,
    question: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Create task + executions from a finished supervisor result. Returns API payload."""
    decision = str(result.get("route_decision") or "")
    task = ai_trace.create_task(
        session_id=session_id,
        question=question,
        task_type=_map_task_type(decision),
    )
    task_id = task["id"]
    ai_trace.mark_task_running(task_id)

    route = list(result.get("route") or [])
    step = 0

    step += 1
    ai_trace.append_execution(
        task_id=task_id,
        agent_name="supervisor",
        step_no=step,
        tool_name="route",
        input_summary=ai_trace.truncate(question, 500),
        output_summary=(
            f"route_decision={decision}; reason={result.get('route_reason') or ''}"
        ),
        status="success",
    )

    data_part = result.get("data") or {}
    if "data_agent" in route:
        step += 1
        ok_data = bool(data_part.get("ok"))
        ai_trace.append_execution(
            task_id=task_id,
            agent_name="data_agent",
            step_no=step,
            tool_name="run_readonly_sql",
            input_summary=ai_trace.truncate(question, 500),
            output_summary=(
                f"row_count={data_part.get('row_count', 0)}"
                if ok_data
                else (data_part.get("error") or result.get("error") or "data failed")
            ),
            sql_text=data_part.get("executed_sql") or data_part.get("sql") or "",
            status="success" if ok_data else "failed",
        )

    anomaly_part = result.get("anomaly") or {}
    if "anomaly_agent" in route:
        step += 1
        ok_a = bool(anomaly_part.get("ok"))
        findings = anomaly_part.get("findings") or {}
        alert_n = len(findings.get("platform_alerts") or []) if isinstance(findings, dict) else 0
        ai_trace.append_execution(
            task_id=task_id,
            agent_name="anomaly_agent",
            step_no=step,
            tool_name="detect_metric_anomalies",
            input_summary=ai_trace.truncate(question, 500),
            output_summary=(
                f"alerts={alert_n}"
                if ok_a
                else (anomaly_part.get("error") or "anomaly failed")
            ),
            status="success" if ok_a else "failed",
        )

    strategy_part = result.get("strategy") or {}
    if "strategy_agent" in route:
        step += 1
        ok_s = bool(strategy_part.get("ok"))
        snap = strategy_part.get("snapshot") or {}
        alert_n = len(snap.get("platform_alerts") or []) if isinstance(snap, dict) else 0
        ai_trace.append_execution(
            task_id=task_id,
            agent_name="strategy_agent",
            step_no=step,
            tool_name="suggest_ops_strategy",
            input_summary=ai_trace.truncate(question, 500),
            output_summary=(
                f"suggestions_only=true; alerts={alert_n}"
                if ok_s
                else (strategy_part.get("error") or "strategy failed")
            ),
            status="success" if ok_s else "failed",
        )

    knowledge_part = result.get("knowledge") or {}
    if "knowledge_agent" in route:
        step += 1
        ok_k = bool(knowledge_part.get("ok"))
        ai_trace.append_execution(
            task_id=task_id,
            agent_name="knowledge_agent",
            step_no=step,
            tool_name="rag_search",
            input_summary=ai_trace.truncate(question, 500),
            output_summary=(
                f"hit_count={knowledge_part.get('hit_count', 0)}; "
                f"no_hit={bool(knowledge_part.get('no_hit'))}"
                if ok_k
                else (knowledge_part.get("error") or "knowledge failed")
            ),
            status="success" if ok_k else "failed",
        )

    if "reject" in route or decision == "reject":
        step += 1
        ai_trace.append_execution(
            task_id=task_id,
            agent_name="reject",
            step_no=step,
            tool_name="policy",
            input_summary=ai_trace.truncate(question, 500),
            output_summary=result.get("error") or "rejected",
            status="failed",
        )

    if result.get("ok"):
        ai_trace.finish_task(
            task_id=task_id,
            status="success",
            result_summary=result.get("answer") or "",
            error_message="",
        )
    else:
        ai_trace.finish_task(
            task_id=task_id,
            status="failed",
            result_summary=result.get("answer") or "",
            error_message=result.get("error") or "supervisor failed",
        )

    return _supervisor_response_payload(
        session_id=session_id,
        task_id=task_id,
        result=result,
    )


def iter_traced_supervisor_stream(
    session_id: str,
    question: str,
    *,
    max_rows: int = 100,
    top_k: int = 5,
) -> Iterator[dict[str, Any]]:
    """Wrap supervisor SSE events with session/task persistence."""
    task = ai_trace.create_task(
        session_id=session_id,
        question=question,
        task_type="mixed",
    )
    task_id = task["id"]
    ai_trace.mark_task_running(task_id)
    yield {
        "event": "meta",
        "phase": "trace",
        "session_id": session_id,
        "task_id": task_id,
        "question": question,
    }

    final: dict[str, Any] | None = None
    routed = False
    step = 0
    try:
        for ev in run_supervisor_stream(question, max_rows=max_rows, top_k=top_k):
            out = {**ev, "session_id": session_id, "task_id": task_id}
            if out.get("event") == "meta" and out.get("phase") == "routed" and not routed:
                routed = True
                step += 1
                decision = str(out.get("route_decision") or "")
                try:
                    ai_trace.update_task_type(task_id, _map_task_type(decision))
                except ValueError:
                    pass
                ai_trace.append_execution(
                    task_id=task_id,
                    agent_name="supervisor",
                    step_no=step,
                    tool_name="route",
                    input_summary=ai_trace.truncate(question, 500),
                    output_summary=(
                        f"route_decision={decision}; reason={out.get('route_reason') or ''}"
                    ),
                    status="success",
                )
            if out.get("event") == "done":
                final = out
            if out.get("event") == "error":
                step += 1
                ai_trace.append_execution(
                    task_id=task_id,
                    agent_name="supervisor",
                    step_no=step,
                    tool_name="error",
                    input_summary=ai_trace.truncate(question, 500),
                    output_summary=out.get("error") or "error",
                    status="failed",
                )
                ai_trace.finish_task(
                    task_id=task_id,
                    status="failed",
                    error_message=out.get("error") or "stream error",
                )
            yield out

        if final is not None:
            route = list(final.get("route") or [])
            decision = str(final.get("route_decision") or "")
            if "data_agent" in route:
                step += 1
                ai_trace.append_execution(
                    task_id=task_id,
                    agent_name="data_agent",
                    step_no=step,
                    tool_name="run_readonly_sql",
                    input_summary=ai_trace.truncate(question, 500),
                    output_summary=f"row_count={final.get('row_count', 0)}",
                    sql_text=final.get("sql") or "",
                    status="success",
                )
            if "anomaly_agent" in route:
                step += 1
                refs = final.get("refs") or []
                alert_n = 0
                for r in refs:
                    if r.get("type") == "anomaly":
                        alert_n = len(r.get("alerts") or [])
                        break
                ai_trace.append_execution(
                    task_id=task_id,
                    agent_name="anomaly_agent",
                    step_no=step,
                    tool_name="detect_metric_anomalies",
                    input_summary=ai_trace.truncate(question, 500),
                    output_summary=f"alerts={alert_n}",
                    status="success",
                )
            if "strategy_agent" in route:
                step += 1
                refs = final.get("refs") or []
                alert_n = 0
                for r in refs:
                    if r.get("type") == "strategy_snapshot":
                        alert_n = len(r.get("alerts") or [])
                        break
                ai_trace.append_execution(
                    task_id=task_id,
                    agent_name="strategy_agent",
                    step_no=step,
                    tool_name="suggest_ops_strategy",
                    input_summary=ai_trace.truncate(question, 500),
                    output_summary=f"suggestions_only=true; alerts={alert_n}",
                    status="success",
                )
            if "knowledge_agent" in route:
                step += 1
                citations = final.get("citations") or []
                ai_trace.append_execution(
                    task_id=task_id,
                    agent_name="knowledge_agent",
                    step_no=step,
                    tool_name="rag_search",
                    input_summary=ai_trace.truncate(question, 500),
                    output_summary=(
                        f"citations={len(citations)}; no_hit={bool(final.get('no_hit'))}"
                    ),
                    status="success",
                )
            if "reject" in route or decision == "reject":
                step += 1
                ai_trace.append_execution(
                    task_id=task_id,
                    agent_name="reject",
                    step_no=step,
                    tool_name="policy",
                    output_summary=final.get("error") or "rejected",
                    status="failed",
                )
            ai_trace.finish_task(
                task_id=task_id,
                status="success",
                result_summary=final.get("answer") or "",
            )
    except Exception as exc:  # noqa: BLE001
        ai_trace.finish_task(
            task_id=task_id,
            status="failed",
            error_message=str(exc),
        )
        yield {
            "event": "error",
            "session_id": session_id,
            "task_id": task_id,
            "error": str(exc),
        }


# --- Sessions / Tasks ---


@router.post("/sessions")
def post_session(
    body: CreateSessionRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    data = ai_trace.create_session(title=body.title, user_id=user.id)
    return ok(data)


@router.get("/sessions")
def get_sessions(
    user: Annotated[AuthUser, Depends(get_current_user)],
    limit: int = 20,
) -> dict:
    _ = user
    return ok(ai_trace.list_sessions(limit=limit))


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    _ = user
    data = ai_trace.get_session(session_id)
    if not data:
        return fail(404, "session not found")
    return ok(data)


@router.get("/tasks/{task_id}")
def get_task(
    task_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    _ = user
    data = ai_trace.get_task(task_id)
    if not data:
        return fail(404, "task not found")
    return ok(data)


@router.get("/tasks/{task_id}/executions")
def get_task_executions(
    task_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    _ = user
    task = ai_trace.get_task(task_id)
    if not task:
        return fail(404, "task not found")
    return ok(ai_trace.list_executions(task_id))


@router.post("/sessions/{session_id}/ask")
def post_session_ask(
    session_id: str,
    body: SupervisorAskRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    _ = user
    if not ai_trace.get_session(session_id):
        return fail(404, "session not found")
    result = run_supervisor(
        body.question,
        max_rows=body.max_rows,
        top_k=body.top_k,
    )
    payload = _persist_supervisor_result(
        session_id=session_id,
        question=body.question,
        result=result,
    )
    if not result.get("ok"):
        return fail(501, result.get("error") or "supervisor failed", payload)
    return ok(payload)


@router.post("/sessions/{session_id}/ask/stream")
def post_session_ask_stream(
    session_id: str,
    body: SupervisorAskRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
):
    _ = user
    if not ai_trace.get_session(session_id):
        return fail(404, "session not found")
    return sse_response(
        iter_traced_supervisor_stream(
            session_id,
            body.question,
            max_rows=body.max_rows,
            top_k=body.top_k,
        )
    )


# --- Legacy direct endpoints (auto-create session + persist for /ask) ---


@router.post("/anomaly")
def post_anomaly(
    body: AskRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    _ = user
    result = analyze_anomaly(body.question)
    if not result.get("ok"):
        return fail(501, result.get("error") or "anomaly failed", result)
    return ok(
        {
            "task_id": result["task_id"],
            "question": result["question"],
            "answer": result["answer"],
            "findings": result.get("findings") or {},
            "refs": result.get("refs") or [],
        }
    )


@router.post("/anomaly/stream")
def post_anomaly_stream(
    body: AskRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
):
    _ = user
    return sse_response(analyze_anomaly_stream(body.question))


@router.post("/strategy")
def post_strategy(
    body: StrategyAskRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    _ = user
    result = analyze_strategy(
        body.question,
        with_knowledge=body.with_knowledge,
        top_k=body.top_k,
    )
    if not result.get("ok"):
        return fail(501, result.get("error") or "strategy failed", result)
    return ok(
        {
            "task_id": result["task_id"],
            "question": result["question"],
            "answer": result["answer"],
            "snapshot": result.get("snapshot") or {},
            "knowledge": result.get("knowledge"),
            "refs": result.get("refs") or [],
            "suggestions_only": True,
        }
    )


@router.post("/strategy/stream")
def post_strategy_stream(
    body: StrategyAskRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
):
    _ = user
    return sse_response(
        analyze_strategy_stream(
            body.question,
            with_knowledge=body.with_knowledge,
            top_k=body.top_k,
        )
    )


@router.post("/nl2sql")
def post_nl2sql(body: AskRequest) -> dict:
    result = analyze_question(body.question, max_rows=body.max_rows)
    if not result.get("ok"):
        return fail(501, result.get("error") or "nl2sql failed", result)
    return ok(
        {
            "task_id": result["task_id"],
            "question": result["question"],
            "sql": result["executed_sql"] or result["sql"],
            "row_count": result["row_count"],
            "rows": result["rows"][:50],
            "answer": result["answer"],
        }
    )


@router.post("/nl2sql/stream")
def post_nl2sql_stream(body: AskRequest):
    return sse_response(analyze_question_stream(body.question, max_rows=body.max_rows))


@router.post("/knowledge")
def post_knowledge(body: KnowledgeAskRequest) -> dict:
    result = answer_knowledge_question(
        body.question,
        top_k=body.top_k,
        doc_type=body.doc_type,
    )
    if not result.get("ok"):
        return fail(501, result.get("error") or "knowledge qa failed", result)
    return ok(
        {
            "task_id": result["task_id"],
            "question": result["question"],
            "answer": result["answer"],
            "citations": result["citations"],
            "hit_count": result["hit_count"],
            "no_hit": result["no_hit"],
        }
    )


@router.post("/knowledge/stream")
def post_knowledge_stream(body: KnowledgeAskRequest):
    return sse_response(
        answer_knowledge_question_stream(
            body.question,
            top_k=body.top_k,
            doc_type=body.doc_type,
        )
    )


@router.post("/ask")
def post_supervisor_ask(
    body: SupervisorAskRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    session = ai_trace.create_session(title=(body.question or "")[:40], user_id=user.id)
    result = run_supervisor(
        body.question,
        max_rows=body.max_rows,
        top_k=body.top_k,
    )
    payload = _persist_supervisor_result(
        session_id=session["id"],
        question=body.question,
        result=result,
    )
    if not result.get("ok"):
        return fail(501, result.get("error") or "supervisor failed", payload)
    return ok(payload)


@router.post("/ask/stream")
def post_supervisor_ask_stream(
    body: SupervisorAskRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
):
    session = ai_trace.create_session(title=(body.question or "")[:40], user_id=user.id)
    return sse_response(
        iter_traced_supervisor_stream(
            session["id"],
            body.question,
            max_rows=body.max_rows,
            top_k=body.top_k,
        )
    )
