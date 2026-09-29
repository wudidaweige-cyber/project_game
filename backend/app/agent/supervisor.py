"""Supervisor: LangGraph route → data/knowledge agents → synthesize."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.anomaly import analyze_anomaly
from app.agent.knowledge import answer_knowledge_question
from app.agent.llm import LLMError, get_llm_client
from app.agent.nl2sql import analyze_question
from app.agent.strategy import analyze_strategy

RouteKind = Literal[
    "data",
    "knowledge",
    "both",
    "anomaly",
    "anomaly_knowledge",
    "strategy",
    "strategy_knowledge",
    "reject",
]

_ROUTE_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)

ROUTER_PROMPT = """你是游戏账号租赁平台的任务路由助手。
根据用户问题，判断应调用哪些能力，只输出一个 JSON 对象，不要其它文字：
{"route":"data"|"knowledge"|"both"|"anomaly"|"anomaly_knowledge"|"strategy"|"strategy_knowledge"|"reject","reason":"简短原因"}

规则：
1. data：查运营指标、GMV、订单量、出租率、排行、趋势等「查数」问题。
2. knowledge：问退款/SOP/上架/风控/定价等规则与流程。
3. anomaly：指标异常、波动、为何下降/上升、异常归因。
4. anomaly_knowledge：异常归因 + 按规则/SOP 处理建议。
5. strategy：要运营策略/优化建议/调价观察/库存倾斜/活动建议（只建议不写库）。
6. strategy_knowledge：策略建议且需要对照定价/运营规则知识。
7. both：普通查数结论 + 规则依据，非异常检测、非策略建议为主。
8. reject：要求改数据、写库、删改订单、直接改价落库、执行 DDL/DML 等 —— 必须拒绝。
""".strip()

SYNTH_PROMPT = """你是运营分析助手。请汇总「数据/异常/策略结论」与「知识结论」回答用户。
要求：
1. 用简洁中文，先给结论再给依据。
2. 只依据给定结论，不编造数字。
3. 若含策略建议，必须强调仅供人工决策、系统不自动改业务数据。
4. 可引用知识来源编号如 [1]。
""".strip()


class SupervisorState(TypedDict, total=False):
    question: str
    max_rows: int
    top_k: int
    task_id: str
    route_decision: RouteKind
    route_reason: str
    route: list[str]
    data_result: dict[str, Any]
    knowledge_result: dict[str, Any]
    anomaly_result: dict[str, Any]
    strategy_result: dict[str, Any]
    answer: str
    refs: list[dict[str, Any]]
    ok: bool
    error: str
    started_at: str


def _parse_route(text: str, question: str = "") -> tuple[RouteKind, str]:
    raw = (text or "").strip()
    m = _ROUTE_RE.search(raw)
    payload: dict[str, Any] = {}
    if m:
        try:
            payload = json.loads(m.group(0))
        except json.JSONDecodeError:
            payload = {}
    route = str(payload.get("route") or "").strip().lower()
    reason = str(payload.get("reason") or "").strip()
    allowed = (
        "data",
        "knowledge",
        "both",
        "anomaly",
        "anomaly_knowledge",
        "strategy",
        "strategy_knowledge",
        "reject",
    )
    if route in allowed:
        return route, reason  # type: ignore[return-value]
    q = question or raw
    if any(k in q for k in ("改成", "删除", "更新订单", "DROP", "INSERT", "UPDATE", "TRUNCATE", "直接改价")):
        return "reject", reason or "疑似写操作"
    anomaly_kw = ("异常", "波动", "下滑", "飙升", "为何下降", "为什么下降", "归因")
    strategy_kw = ("策略", "建议", "怎么优化", "如何优化", "调价", "库存倾斜", "活动建议", "运营建议")
    rule_kw = ("退款", "SOP", "上架", "冻结", "规则", "流程", "违规", "定价规则")
    has_anomaly = any(k in q for k in anomaly_kw)
    has_strategy = any(k in q for k in strategy_kw)
    has_rule = any(k in q for k in rule_kw)
    if has_strategy and has_rule:
        return "strategy_knowledge", reason or "启发式策略+规则"
    if has_strategy:
        return "strategy", reason or "启发式策略分析"
    if has_anomaly and has_rule:
        return "anomaly_knowledge", reason or "启发式异常+规则"
    if has_anomaly:
        return "anomaly", reason or "启发式异常分析"
    if has_rule:
        if any(k in q for k in ("GMV", "出租率", "订单", "多少", "排行")):
            return "both", reason or "启发式双路"
        return "knowledge", reason or "启发式知识"
    return "data", reason or "默认走数据分析"


def _classify(state: SupervisorState) -> dict[str, Any]:
    llm = get_llm_client()
    content = llm.chat(
        [
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user", "content": f"用户问题：{state['question']}"},
        ],
        temperature=0.0,
    )
    decision, reason = _parse_route(content, question=state["question"])
    route = list(state.get("route") or [])
    route.append("supervisor")
    return {
        "route_decision": decision,
        "route_reason": reason,
        "route": route,
    }


def _run_data(state: SupervisorState) -> dict[str, Any]:
    result = analyze_question(state["question"], max_rows=int(state.get("max_rows") or 100))
    route = list(state.get("route") or [])
    route.append("data_agent")
    return {"data_result": result, "route": route}


def _run_anomaly(state: SupervisorState) -> dict[str, Any]:
    result = analyze_anomaly(state["question"])
    route = list(state.get("route") or [])
    route.append("anomaly_agent")
    return {"anomaly_result": result, "route": route}


def _run_strategy(state: SupervisorState) -> dict[str, Any]:
    with_knowledge = (state.get("route_decision") or "") == "strategy_knowledge"
    result = analyze_strategy(
        state["question"],
        with_knowledge=with_knowledge,
        top_k=int(state.get("top_k") or 5),
    )
    route = list(state.get("route") or [])
    route.append("strategy_agent")
    if with_knowledge:
        route.append("knowledge_agent")
        return {
            "strategy_result": result,
            "knowledge_result": result.get("knowledge") or {},
            "route": route,
        }
    return {"strategy_result": result, "route": route}


def _run_knowledge(state: SupervisorState) -> dict[str, Any]:
    result = answer_knowledge_question(
        state["question"],
        top_k=int(state.get("top_k") or 5),
    )
    route = list(state.get("route") or [])
    route.append("knowledge_agent")
    return {"knowledge_result": result, "route": route}


def _reject(state: SupervisorState) -> dict[str, Any]:
    route = list(state.get("route") or [])
    if "reject" not in route:
        route.append("reject")
    return {
        "ok": False,
        "error": "安全策略拒绝：不允许通过对话执行写库或修改业务数据的操作。",
        "answer": "",
        "route": route,
        "refs": [],
    }


def _build_refs(state: SupervisorState) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    data = state.get("data_result") or {}
    if data.get("ok"):
        sql = data.get("executed_sql") or data.get("sql") or ""
        refs.append(
            {
                "type": "sql",
                "summary": sql[:500],
                "row_count": data.get("row_count", 0),
            }
        )
    anomaly = state.get("anomaly_result") or {}
    if anomaly.get("ok"):
        for r in anomaly.get("refs") or []:
            refs.append(r)
    strategy = state.get("strategy_result") or {}
    if strategy.get("ok"):
        for r in strategy.get("refs") or []:
            refs.append(r)
    knowledge = state.get("knowledge_result") or {}
    if knowledge.get("ok"):
        for c in knowledge.get("citations") or []:
            refs.append(
                {
                    "type": "knowledge",
                    "index": c.get("index"),
                    "title": c.get("title"),
                    "doc_type": c.get("doc_type"),
                    "source_path": c.get("source_path"),
                    "score": c.get("score"),
                    "snippet": c.get("snippet"),
                }
            )
    return refs


def _synthesize(state: SupervisorState) -> dict[str, Any]:
    decision = state.get("route_decision") or "data"
    data = state.get("data_result") or {}
    knowledge = state.get("knowledge_result") or {}
    anomaly = state.get("anomaly_result") or {}
    refs = _build_refs(state)

    if decision == "data":
        if not data.get("ok"):
            return {
                "ok": False,
                "error": data.get("error") or "数据分析失败",
                "answer": "",
                "refs": refs,
            }
        return {
            "ok": True,
            "answer": data.get("answer") or "",
            "error": "",
            "refs": refs,
        }

    if decision == "knowledge":
        if not knowledge.get("ok"):
            return {
                "ok": False,
                "error": knowledge.get("error") or "知识问答失败",
                "answer": "",
                "refs": refs,
            }
        return {
            "ok": True,
            "answer": knowledge.get("answer") or "",
            "error": "",
            "refs": refs,
        }

    if decision == "anomaly":
        if not anomaly.get("ok"):
            return {
                "ok": False,
                "error": anomaly.get("error") or "异常分析失败",
                "answer": "",
                "refs": refs,
            }
        return {
            "ok": True,
            "answer": anomaly.get("answer") or "",
            "error": "",
            "refs": refs,
        }

    if decision in ("strategy", "strategy_knowledge"):
        strategy = state.get("strategy_result") or {}
        if not strategy.get("ok"):
            return {
                "ok": False,
                "error": strategy.get("error") or "策略分析失败",
                "answer": "",
                "refs": refs,
            }
        return {
            "ok": True,
            "answer": strategy.get("answer") or "",
            "error": "",
            "refs": refs,
        }

    # both / anomaly_knowledge
    if decision == "anomaly_knowledge":
        left = anomaly
        left_label = "异常结论"
        left_fail = "异常侧失败"
    else:
        left = data
        left_label = "数据结论"
        left_fail = "数据侧失败"

    if not left.get("ok") and not knowledge.get("ok"):
        return {
            "ok": False,
            "error": left.get("error") or knowledge.get("error") or "双路均失败",
            "answer": "",
            "refs": refs,
        }

    left_part = left.get("answer") if left.get("ok") else f"（{left_fail}：{left.get('error') or '未知'}）"
    knowledge_part = (
        knowledge.get("answer")
        if knowledge.get("ok")
        else f"（知识侧失败：{knowledge.get('error') or '未知'}）"
    )

    try:
        llm = get_llm_client()
        answer = llm.chat(
            _synth_messages(state["question"], left_part, knowledge_part, left_label=left_label),
            temperature=0.2,
        ).strip()
    except LLMError as exc:
        answer = f"【{left_label}】\n{left_part}\n\n【规则】\n{knowledge_part}"
        if not answer.strip():
            return {"ok": False, "error": str(exc), "answer": "", "refs": refs}

    if not answer:
        return {"ok": False, "error": "汇总结果为空", "answer": "", "refs": refs}

    return {"ok": True, "answer": answer, "error": "", "refs": refs}


def _synth_messages(
    question: str,
    data_part: str,
    knowledge_part: str,
    *,
    left_label: str = "数据结论",
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYNTH_PROMPT},
        {
            "role": "user",
            "content": (
                f"用户问题：{question}\n\n"
                f"【{left_label}】\n{data_part}\n\n"
                f"【知识结论】\n{knowledge_part}\n\n"
                "请汇总回答。"
            ),
        },
    ]


def _after_classify(state: SupervisorState) -> str:
    decision = state.get("route_decision") or "data"
    if decision == "reject":
        return "reject"
    if decision == "knowledge":
        return "knowledge"
    if decision == "both":
        return "data_then_knowledge"
    if decision == "anomaly":
        return "anomaly"
    if decision == "anomaly_knowledge":
        return "anomaly_then_knowledge"
    if decision in ("strategy", "strategy_knowledge"):
        return "strategy"
    return "data"


def _after_data(state: SupervisorState) -> str:
    if (state.get("route_decision") or "") == "both":
        return "knowledge"
    return "synthesize"


def _after_anomaly(state: SupervisorState) -> str:
    if (state.get("route_decision") or "") == "anomaly_knowledge":
        return "knowledge"
    return "synthesize"


def build_supervisor_graph():
    graph = StateGraph(SupervisorState)
    graph.add_node("classify", _classify)
    graph.add_node("data", _run_data)
    graph.add_node("anomaly", _run_anomaly)
    graph.add_node("strategy", _run_strategy)
    graph.add_node("knowledge", _run_knowledge)
    graph.add_node("reject", _reject)
    graph.add_node("synthesize", _synthesize)

    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify",
        _after_classify,
        {
            "data": "data",
            "knowledge": "knowledge",
            "data_then_knowledge": "data",
            "anomaly": "anomaly",
            "anomaly_then_knowledge": "anomaly",
            "strategy": "strategy",
            "reject": "reject",
        },
    )
    graph.add_conditional_edges(
        "data",
        _after_data,
        {"knowledge": "knowledge", "synthesize": "synthesize"},
    )
    graph.add_conditional_edges(
        "anomaly",
        _after_anomaly,
        {"knowledge": "knowledge", "synthesize": "synthesize"},
    )
    graph.add_edge("strategy", "synthesize")
    graph.add_edge("knowledge", "synthesize")
    graph.add_edge("reject", END)
    graph.add_edge("synthesize", END)
    return graph.compile()

_GRAPH = None


def get_supervisor_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_supervisor_graph()
    return _GRAPH


def run_supervisor(
    question: str,
    *,
    max_rows: int = 100,
    top_k: int = 5,
) -> dict[str, Any]:
    task_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    base: dict[str, Any] = {
        "ok": False,
        "task_id": task_id,
        "question": question,
        "answer": "",
        "route": [],
        "route_decision": "",
        "route_reason": "",
        "refs": [],
        "data": None,
        "knowledge": None,
        "anomaly": None,
        "strategy": None,
        "error": "",
        "started_at": started.isoformat(),
    }

    q = (question or "").strip()
    if not q:
        base["error"] = "问题为空"
        return base

    try:
        graph = get_supervisor_graph()
        final: SupervisorState = graph.invoke(
            {
                "question": q,
                "max_rows": max_rows,
                "top_k": top_k,
                "task_id": task_id,
                "route": [],
                "started_at": started.isoformat(),
            }
        )
        base["route"] = list(final.get("route") or [])
        base["route_decision"] = final.get("route_decision") or ""
        base["route_reason"] = final.get("route_reason") or ""
        base["answer"] = final.get("answer") or ""
        base["refs"] = list(final.get("refs") or [])
        base["data"] = final.get("data_result")
        base["knowledge"] = final.get("knowledge_result")
        base["anomaly"] = final.get("anomaly_result")
        base["strategy"] = final.get("strategy_result")
        base["ok"] = bool(final.get("ok"))
        base["error"] = final.get("error") or ""
        return base
    except LLMError as exc:
        base["error"] = str(exc)
        return base
    except Exception as exc:  # noqa: BLE001
        base["error"] = f"Supervisor 执行失败: {exc}"
        return base


def run_supervisor_stream(
    question: str,
    *,
    max_rows: int = 100,
    top_k: int = 5,
):
    """Yield SSE events: route → agent work → token stream → done."""
    from app.agent.anomaly import analyze_anomaly_stream
    from app.agent.knowledge import answer_knowledge_question_stream
    from app.agent.nl2sql import analyze_question_stream
    from app.agent.strategy import analyze_strategy_stream

    task_id = str(uuid.uuid4())
    q = (question or "").strip()
    yield {"event": "meta", "task_id": task_id, "phase": "start", "question": q}
    if not q:
        yield {"event": "error", "task_id": task_id, "error": "问题为空"}
        return

    try:
        yield {"event": "phase", "task_id": task_id, "phase": "routing"}
        classified = _classify({"question": q, "route": []})
        decision = classified["route_decision"]
        reason = classified.get("route_reason") or ""
        route = list(classified.get("route") or ["supervisor"])
        yield {
            "event": "meta",
            "task_id": task_id,
            "phase": "routed",
            "route_decision": decision,
            "route_reason": reason,
            "route": route,
        }

        if decision == "reject":
            err = "安全策略拒绝：不允许通过对话执行写库或修改业务数据的操作。"
            yield {
                "event": "error",
                "task_id": task_id,
                "error": err,
                "route": route + ["reject"],
                "route_decision": decision,
            }
            return

        data_result: dict[str, Any] | None = None
        knowledge_result: dict[str, Any] | None = None
        anomaly_result: dict[str, Any] | None = None

        if decision in ("strategy", "strategy_knowledge"):
            yield {"event": "phase", "task_id": task_id, "phase": "strategy_agent"}
            with_knowledge = decision == "strategy_knowledge"
            final_done = None
            for ev in analyze_strategy_stream(
                q, with_knowledge=with_knowledge, top_k=top_k
            ):
                et = ev.get("event")
                if et == "token":
                    yield {**ev, "task_id": task_id}
                elif et == "error":
                    yield {
                        "event": "error",
                        "task_id": task_id,
                        "error": ev.get("error") or "策略分析失败",
                        "route": route
                        + (["strategy_agent", "knowledge_agent"] if with_knowledge else ["strategy_agent"]),
                        "route_decision": decision,
                    }
                    return
                elif et == "done":
                    final_done = ev
                elif et in ("phase", "meta"):
                    yield {**ev, "task_id": task_id}
            route = route + ["strategy_agent"]
            if with_knowledge:
                route = route + ["knowledge_agent"]
            citations = (final_done or {}).get("citations") or []
            yield {
                "event": "done",
                "task_id": task_id,
                "question": q,
                "answer": (final_done or {}).get("answer") or "",
                "route": route,
                "route_decision": decision,
                "route_reason": reason,
                "refs": (final_done or {}).get("refs") or [],
                "sql": "",
                "row_count": 0,
                "citations": citations,
                "no_hit": False,
                "suggestions_only": True,
                "snapshot": (final_done or {}).get("snapshot") or {},
            }
            return

        if decision in ("data", "both"):
            yield {"event": "phase", "task_id": task_id, "phase": "data_agent"}
            if decision == "data":
                final_done: dict[str, Any] | None = None
                for ev in analyze_question_stream(q, max_rows=max_rows):
                    et = ev.get("event")
                    if et == "token":
                        yield {**ev, "task_id": task_id}
                    elif et == "error":
                        yield {
                            "event": "error",
                            "task_id": task_id,
                            "error": ev.get("error") or "数据分析失败",
                            "sql": ev.get("sql") or "",
                            "route": route + ["data_agent"],
                            "route_decision": decision,
                        }
                        return
                    elif et == "done":
                        final_done = ev
                    elif et in ("phase", "meta"):
                        yield {**ev, "task_id": task_id}
                route = route + ["data_agent"]
                answer = (final_done or {}).get("answer") or ""
                refs = [
                    {
                        "type": "sql",
                        "summary": (final_done or {}).get("sql") or "",
                        "row_count": (final_done or {}).get("row_count", 0),
                    }
                ]
                yield {
                    "event": "done",
                    "task_id": task_id,
                    "question": q,
                    "answer": answer,
                    "route": route,
                    "route_decision": decision,
                    "route_reason": reason,
                    "refs": refs,
                    "sql": (final_done or {}).get("sql") or "",
                    "row_count": (final_done or {}).get("row_count", 0),
                    "citations": [],
                    "no_hit": False,
                }
                return

            data_result = analyze_question(q, max_rows=max_rows)
            route = route + ["data_agent"]
            yield {
                "event": "meta",
                "task_id": task_id,
                "phase": "data_done",
                "ok": bool(data_result.get("ok")),
                "error": data_result.get("error") or "",
                "sql": data_result.get("executed_sql") or data_result.get("sql") or "",
            }

        if decision in ("anomaly", "anomaly_knowledge"):
            yield {"event": "phase", "task_id": task_id, "phase": "anomaly_agent"}
            if decision == "anomaly":
                final_done = None
                for ev in analyze_anomaly_stream(q):
                    et = ev.get("event")
                    if et == "token":
                        yield {**ev, "task_id": task_id}
                    elif et == "error":
                        yield {
                            "event": "error",
                            "task_id": task_id,
                            "error": ev.get("error") or "异常分析失败",
                            "route": route + ["anomaly_agent"],
                            "route_decision": decision,
                        }
                        return
                    elif et == "done":
                        final_done = ev
                    elif et in ("phase", "meta"):
                        yield {**ev, "task_id": task_id}
                route = route + ["anomaly_agent"]
                yield {
                    "event": "done",
                    "task_id": task_id,
                    "question": q,
                    "answer": (final_done or {}).get("answer") or "",
                    "route": route,
                    "route_decision": decision,
                    "route_reason": reason,
                    "refs": (final_done or {}).get("refs") or [],
                    "sql": "",
                    "row_count": 0,
                    "citations": [],
                    "no_hit": False,
                }
                return

            anomaly_result = analyze_anomaly(q)
            route = route + ["anomaly_agent"]
            yield {
                "event": "meta",
                "task_id": task_id,
                "phase": "anomaly_done",
                "ok": bool(anomaly_result.get("ok")),
                "error": anomaly_result.get("error") or "",
            }

        if decision in ("knowledge", "both", "anomaly_knowledge"):
            yield {"event": "phase", "task_id": task_id, "phase": "knowledge_agent"}
            if decision == "knowledge":
                final_done = None
                for ev in answer_knowledge_question_stream(q, top_k=top_k):
                    et = ev.get("event")
                    if et == "token":
                        yield {**ev, "task_id": task_id}
                    elif et == "error":
                        yield {
                            "event": "error",
                            "task_id": task_id,
                            "error": ev.get("error") or "知识问答失败",
                            "route": route + ["knowledge_agent"],
                            "route_decision": decision,
                        }
                        return
                    elif et == "done":
                        final_done = ev
                    elif et in ("phase", "meta"):
                        yield {**ev, "task_id": task_id}
                route = route + ["knowledge_agent"]
                citations = (final_done or {}).get("citations") or []
                refs = [
                    {
                        "type": "knowledge",
                        "index": c.get("index"),
                        "title": c.get("title"),
                        "doc_type": c.get("doc_type"),
                        "source_path": c.get("source_path"),
                        "score": c.get("score"),
                        "snippet": c.get("snippet"),
                    }
                    for c in citations
                ]
                yield {
                    "event": "done",
                    "task_id": task_id,
                    "question": q,
                    "answer": (final_done or {}).get("answer") or "",
                    "route": route,
                    "route_decision": decision,
                    "route_reason": reason,
                    "refs": refs,
                    "sql": "",
                    "row_count": 0,
                    "citations": citations,
                    "no_hit": bool((final_done or {}).get("no_hit")),
                }
                return

            knowledge_result = answer_knowledge_question(q, top_k=top_k)
            route = route + ["knowledge_agent"]
            yield {
                "event": "meta",
                "task_id": task_id,
                "phase": "knowledge_done",
                "ok": bool(knowledge_result.get("ok")),
                "hit_count": knowledge_result.get("hit_count", 0),
                "no_hit": bool(knowledge_result.get("no_hit")),
            }

        # both / anomaly_knowledge → synthesize stream
        state: SupervisorState = {
            "question": q,
            "route_decision": decision,  # type: ignore[typeddict-item]
            "data_result": data_result or {},
            "knowledge_result": knowledge_result or {},
            "anomaly_result": anomaly_result or {},
            "route": route,
        }
        synth = _synthesize(state)
        refs = synth.get("refs") or _build_refs(state)
        if not synth.get("ok"):
            yield {
                "event": "error",
                "task_id": task_id,
                "error": synth.get("error") or "汇总失败",
                "route": route,
                "route_decision": decision,
                "refs": refs,
            }
            return

        left = anomaly_result if decision == "anomaly_knowledge" else data_result
        left_label = "异常结论" if decision == "anomaly_knowledge" else "数据结论"
        left_part = (
            (left or {}).get("answer")
            if (left or {}).get("ok")
            else f"（{left_label}失败：{(left or {}).get('error') or '未知'}）"
        )
        knowledge = knowledge_result or {}
        knowledge_part = (
            knowledge.get("answer")
            if knowledge.get("ok")
            else f"（知识侧失败：{knowledge.get('error') or '未知'}）"
        )

        yield {"event": "phase", "task_id": task_id, "phase": "synthesizing"}
        llm = get_llm_client()
        parts: list[str] = []
        try:
            for piece in llm.chat_stream(
                _synth_messages(q, left_part or "", knowledge_part, left_label=left_label),
                temperature=0.2,
            ):
                parts.append(piece)
                yield {"event": "token", "task_id": task_id, "text": piece}
            answer = "".join(parts).strip()
        except LLMError:
            answer = synth.get("answer") or f"【{left_label}】\n{left_part}\n\n【规则】\n{knowledge_part}"
            for piece in answer:
                yield {"event": "token", "task_id": task_id, "text": piece}

        if not answer:
            yield {"event": "error", "task_id": task_id, "error": "汇总结果为空", "route": route}
            return

        citations = (knowledge or {}).get("citations") or []
        yield {
            "event": "done",
            "task_id": task_id,
            "question": q,
            "answer": answer,
            "route": route,
            "route_decision": decision,
            "route_reason": reason,
            "refs": refs,
            "sql": (data_result or {}).get("executed_sql") or (data_result or {}).get("sql") or "",
            "row_count": (data_result or {}).get("row_count", 0),
            "citations": citations,
            "no_hit": bool((knowledge or {}).get("no_hit")),
        }
    except LLMError as exc:
        yield {"event": "error", "task_id": task_id, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        yield {"event": "error", "task_id": task_id, "error": f"Supervisor 执行失败: {exc}"}
