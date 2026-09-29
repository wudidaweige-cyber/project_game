"""Strategy analysis agent: metrics snapshot → suggest-only recommendations."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.agent.llm import LLMError, get_llm_client
from app.agent.knowledge import answer_knowledge_question
from app.services.anomaly import detect_metric_anomalies

SYSTEM_PROMPT = """你是游戏账号租赁平台的运营策略分析助手。
只能依据给定的指标快照与（可选）知识片段给出建议。
硬性约束：
1. 只输出「建议」，不得声称已改价、已上下架、已执行写库。
2. 每条建议注明依据（指标或知识编号），数据不足时明确说限制条件。
3. 用简洁中文，结构建议：结论摘要 → 分条建议（观察调价/库存/活动/风控等）→ 风险提示。
4. 结尾固定加一句：以上仅为人工决策参考，系统不会自动修改业务数据。
""".strip()

_WINDOW_RE = re.compile(r"(最近|近)\s*(\d+)\s*天")
_WRITE_INTENT_RE = re.compile(
    r"(改成|修改价格|直接调价|自动上架|自动下架|执行写库|UPDATE\s|INSERT\s|DELETE\s)",
    re.IGNORECASE,
)


def _infer_window_days(question: str, default: int = 7) -> int:
    m = _WINDOW_RE.search(question or "")
    if not m:
        return default
    try:
        return max(3, min(int(m.group(2)), 30))
    except ValueError:
        return default


def _format_snapshot(report: dict[str, Any]) -> str:
    if not report.get("has_data"):
        return report.get("message") or "无可用指标数据"
    lines = [
        f"窗口：近期 {report['recent']['start']}~{report['recent']['end']} "
        f"vs 基期 {report['baseline']['start']}~{report['baseline']['end']} "
        f"（各 {report['window_days']} 天）"
    ]
    for m in report.get("all_metrics") or []:
        lines.append(
            f"- {m.get('label')}: 近期={m.get('recent_value')}，基期={m.get('baseline_value')}"
        )
    alerts = report.get("platform_alerts") or []
    if alerts:
        lines.append("显著波动指标：")
        for a in alerts:
            lines.append(
                f"  · {a.get('label')} 方向={a.get('direction')} "
                f"变化={a.get('change_ratio')}"
            )
            for g in (a.get("top_games") or [])[:3]:
                lines.append(
                    f"    - {g.get('game_name')}: Δ={g.get('delta')}, "
                    f"变化比={g.get('change_ratio')}"
                )
    else:
        lines.append(report.get("message") or "无超过阈值的显著异常，可给稳健观察建议。")
    return "\n".join(lines)


def analyze_strategy(
    question: str,
    *,
    window_days: int | None = None,
    with_knowledge: bool = False,
    top_k: int = 5,
) -> dict[str, Any]:
    task_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    base: dict[str, Any] = {
        "ok": False,
        "task_id": task_id,
        "question": question,
        "answer": "",
        "snapshot": {},
        "knowledge": None,
        "refs": [],
        "suggestions_only": True,
        "error": "",
        "started_at": started.isoformat(),
    }
    q = (question or "").strip()
    if not q:
        base["error"] = "问题为空"
        return base

    if _WRITE_INTENT_RE.search(q):
        base["error"] = "安全策略拒绝：策略分析仅输出建议，不允许通过对话执行写库或改价落库。"
        return base

    days = window_days if window_days is not None else _infer_window_days(q)
    try:
        report = detect_metric_anomalies(window_days=days)
        base["snapshot"] = report
        base["refs"].append(
            {
                "type": "strategy_snapshot",
                "summary": (
                    f"window={days}d alerts={len(report.get('platform_alerts') or [])}"
                ),
                "alerts": report.get("platform_alerts") or [],
            }
        )
        snapshot_text = _format_snapshot(report)
        knowledge_text = ""
        if with_knowledge:
            kn = answer_knowledge_question(q, top_k=top_k, doc_type=None)
            base["knowledge"] = kn
            if kn.get("ok"):
                knowledge_text = kn.get("answer") or ""
                for c in kn.get("citations") or []:
                    base["refs"].append(
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
            else:
                knowledge_text = f"（知识检索失败：{kn.get('error') or '未知'}）"

        if not report.get("has_data"):
            base["answer"] = (
                f"{snapshot_text}\n\n"
                "数据不足以支撑具体运营策略建议。请确认日指标已灌数后再试。"
                "\n以上仅为人工决策参考，系统不会自动修改业务数据。"
            )
            base["ok"] = True
            return base

        user_content = (
            f"用户问题：{q}\n\n"
            f"【指标快照】\n{snapshot_text}\n\n"
        )
        if with_knowledge:
            user_content += f"【知识结论】\n{knowledge_text or '无知识命中'}\n\n"
        user_content += "请给出可执行的运营策略建议（只建议不落库）。"

        llm = get_llm_client()
        answer = llm.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        ).strip()
        if answer and "不会自动修改业务数据" not in answer:
            answer = answer + "\n\n以上仅为人工决策参考，系统不会自动修改业务数据。"
        base["answer"] = answer or snapshot_text
        base["ok"] = True
        return base
    except LLMError as exc:
        if base.get("snapshot"):
            base["answer"] = (
                f"{_format_snapshot(base['snapshot'])}\n\n"
                f"（模型总结失败：{exc}）\n"
                "以上仅为人工决策参考，系统不会自动修改业务数据。"
            )
            base["ok"] = True
            base["error"] = str(exc)
            return base
        base["error"] = str(exc)
        return base
    except Exception as exc:  # noqa: BLE001
        base["error"] = f"策略分析失败: {exc}"
        return base


def analyze_strategy_stream(
    question: str,
    *,
    window_days: int | None = None,
    with_knowledge: bool = False,
    top_k: int = 5,
):
    task_id = str(uuid.uuid4())
    q = (question or "").strip()
    yield {"event": "meta", "task_id": task_id, "phase": "start", "question": q}
    if not q:
        yield {"event": "error", "task_id": task_id, "error": "问题为空"}
        return
    if _WRITE_INTENT_RE.search(q):
        yield {
            "event": "error",
            "task_id": task_id,
            "error": "安全策略拒绝：策略分析仅输出建议，不允许写库。",
        }
        return

    days = window_days if window_days is not None else _infer_window_days(q)
    try:
        yield {"event": "phase", "task_id": task_id, "phase": "snapshot"}
        report = detect_metric_anomalies(window_days=days)
        snapshot_text = _format_snapshot(report)
        yield {
            "event": "meta",
            "task_id": task_id,
            "phase": "snapshot_done",
            "has_data": bool(report.get("has_data")),
            "alert_count": len(report.get("platform_alerts") or []),
        }

        knowledge_text = ""
        citations: list[dict[str, Any]] = []
        if with_knowledge:
            yield {"event": "phase", "task_id": task_id, "phase": "knowledge"}
            kn = answer_knowledge_question(q, top_k=top_k)
            if kn.get("ok"):
                knowledge_text = kn.get("answer") or ""
                citations = kn.get("citations") or []
            else:
                knowledge_text = f"（知识检索失败：{kn.get('error') or '未知'}）"

        if not report.get("has_data"):
            answer = (
                f"{snapshot_text}\n\n数据不足以支撑具体运营策略建议。"
                "\n以上仅为人工决策参考，系统不会自动修改业务数据。"
            )
            for ch in answer:
                yield {"event": "token", "task_id": task_id, "text": ch}
            yield {
                "event": "done",
                "task_id": task_id,
                "question": q,
                "answer": answer,
                "snapshot": report,
                "citations": citations,
                "refs": [{"type": "strategy_snapshot", "summary": snapshot_text[:200]}],
                "suggestions_only": True,
            }
            return

        user_content = (
            f"用户问题：{q}\n\n【指标快照】\n{snapshot_text}\n\n"
        )
        if with_knowledge:
            user_content += f"【知识结论】\n{knowledge_text or '无知识命中'}\n\n"
        user_content += "请给出可执行的运营策略建议（只建议不落库）。"

        yield {"event": "phase", "task_id": task_id, "phase": "answering"}
        llm = get_llm_client()
        parts: list[str] = []
        for piece in llm.chat_stream(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        ):
            parts.append(piece)
            yield {"event": "token", "task_id": task_id, "text": piece}
        answer = "".join(parts).strip() or snapshot_text
        if "不会自动修改业务数据" not in answer:
            suffix = "\n\n以上仅为人工决策参考，系统不会自动修改业务数据。"
            answer += suffix
            yield {"event": "token", "task_id": task_id, "text": suffix}
        yield {
            "event": "done",
            "task_id": task_id,
            "question": q,
            "answer": answer,
            "snapshot": report,
            "citations": citations,
            "refs": [
                {
                    "type": "strategy_snapshot",
                    "summary": snapshot_text[:400],
                    "alerts": report.get("platform_alerts") or [],
                }
            ]
            + [
                {
                    "type": "knowledge",
                    "index": c.get("index"),
                    "title": c.get("title"),
                    "doc_type": c.get("doc_type"),
                    "snippet": c.get("snippet"),
                }
                for c in citations
            ],
            "suggestions_only": True,
        }
    except LLMError as exc:
        yield {"event": "error", "task_id": task_id, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        yield {"event": "error", "task_id": task_id, "error": f"策略分析失败: {exc}"}
