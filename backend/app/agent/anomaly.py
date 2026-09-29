"""Anomaly analysis agent: detect metric swings → grounded Chinese conclusion."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.agent.llm import LLMError, get_llm_client
from app.services.anomaly import detect_metric_anomalies

SYSTEM_PROMPT = """你是游戏账号租赁平台的异常分析助手。
只能依据给定的指标对比结果作答，不得编造未提供的数字或原因。
要求：
1. 用简洁中文：先给是否异常的结论，再列异常指标与贡献游戏。
2. 若无显著异常或数据不足，明确说明，不要硬编异常。
3. 可给出「可能关注点」，但需标注为基于数据波动的推测，不是已证实根因。
4. 不要输出 SQL 或无关内容。
""".strip()

_WINDOW_RE = re.compile(r"(最近|近)\s*(\d+)\s*天")


def _infer_window_days(question: str, default: int = 7) -> int:
    m = _WINDOW_RE.search(question or "")
    if not m:
        return default
    try:
        n = int(m.group(2))
        return max(3, min(n, 30))
    except ValueError:
        return default


def _format_ratio(v: float | None) -> str:
    if v is None:
        return "基期为0，无法算相对变化"
    return f"{v * 100:.1f}%"


def _format_findings(report: dict[str, Any]) -> str:
    if not report.get("has_data"):
        return report.get("message") or "无数据"
    lines = [
        f"对比窗口：近期 {report['recent']['start']}~{report['recent']['end']} "
        f"vs 基期 {report['baseline']['start']}~{report['baseline']['end']} "
        f"（各 {report['window_days']} 天）"
    ]
    alerts = report.get("platform_alerts") or []
    if not alerts:
        lines.append(report.get("message") or "无显著异常")
        return "\n".join(lines)
    for a in alerts:
        lines.append(
            f"- {a['label']}：近期={a['recent_value']:.4f}，基期={a['baseline_value']:.4f}，"
            f"变化={_format_ratio(a.get('change_ratio'))}，方向={a.get('direction')}"
        )
        tops = a.get("top_games") or []
        if tops:
            parts = []
            for g in tops[:3]:
                parts.append(
                    f"{g.get('game_name')}(Δ={g.get('delta'):.4f}, "
                    f"{_format_ratio(g.get('change_ratio'))})"
                )
            lines.append("  贡献游戏：" + "；".join(parts))
    return "\n".join(lines)


def analyze_anomaly(
    question: str,
    *,
    window_days: int | None = None,
) -> dict[str, Any]:
    task_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    base: dict[str, Any] = {
        "ok": False,
        "task_id": task_id,
        "question": question,
        "answer": "",
        "findings": {},
        "refs": [],
        "error": "",
        "started_at": started.isoformat(),
    }
    q = (question or "").strip()
    if not q:
        base["error"] = "问题为空"
        return base

    days = window_days if window_days is not None else _infer_window_days(q)
    try:
        report = detect_metric_anomalies(window_days=days)
        base["findings"] = report
        base["refs"] = [
            {
                "type": "anomaly",
                "summary": (
                    f"window={days}d recent={report.get('recent')} "
                    f"alerts={len(report.get('platform_alerts') or [])}"
                ),
                "alerts": report.get("platform_alerts") or [],
            }
        ]
        findings_text = _format_findings(report)
        if not report.get("has_data") or not (report.get("platform_alerts") or []):
            base["answer"] = findings_text
            base["ok"] = True
            return base

        llm = get_llm_client()
        answer = llm.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"用户问题：{q}\n\n"
                        f"指标对比结果：\n{findings_text}\n\n"
                        "请给出异常分析结论。"
                    ),
                },
            ],
            temperature=0.2,
        ).strip()
        base["answer"] = answer or findings_text
        base["ok"] = True
        return base
    except LLMError as exc:
        # Still return findings if detection succeeded
        if base.get("findings"):
            base["answer"] = _format_findings(base["findings"])
            base["ok"] = True
            base["error"] = f"模型总结失败，已返回结构化结果：{exc}"
            return base
        base["error"] = str(exc)
        return base
    except Exception as exc:  # noqa: BLE001
        base["error"] = f"异常分析失败: {exc}"
        return base


def analyze_anomaly_stream(question: str, *, window_days: int | None = None):
    """Yield SSE-like events; tokens for LLM summary when available."""
    task_id = str(uuid.uuid4())
    q = (question or "").strip()
    yield {"event": "meta", "task_id": task_id, "phase": "start", "question": q}
    if not q:
        yield {"event": "error", "task_id": task_id, "error": "问题为空"}
        return

    days = window_days if window_days is not None else _infer_window_days(q)
    try:
        yield {"event": "phase", "task_id": task_id, "phase": "detecting"}
        report = detect_metric_anomalies(window_days=days)
        findings_text = _format_findings(report)
        yield {
            "event": "meta",
            "task_id": task_id,
            "phase": "detected",
            "alert_count": len(report.get("platform_alerts") or []),
            "has_data": bool(report.get("has_data")),
        }

        if not report.get("has_data") or not (report.get("platform_alerts") or []):
            for ch in findings_text:
                yield {"event": "token", "task_id": task_id, "text": ch}
            yield {
                "event": "done",
                "task_id": task_id,
                "question": q,
                "answer": findings_text,
                "findings": report,
                "refs": [{"type": "anomaly", "summary": findings_text[:200], "alerts": []}],
            }
            return

        yield {"event": "phase", "task_id": task_id, "phase": "answering"}
        llm = get_llm_client()
        parts: list[str] = []
        for piece in llm.chat_stream(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"用户问题：{q}\n\n"
                        f"指标对比结果：\n{findings_text}\n\n"
                        "请给出异常分析结论。"
                    ),
                },
            ],
            temperature=0.2,
        ):
            parts.append(piece)
            yield {"event": "token", "task_id": task_id, "text": piece}
        answer = "".join(parts).strip() or findings_text
        yield {
            "event": "done",
            "task_id": task_id,
            "question": q,
            "answer": answer,
            "findings": report,
            "refs": [
                {
                    "type": "anomaly",
                    "summary": findings_text[:400],
                    "alerts": report.get("platform_alerts") or [],
                }
            ],
        }
    except LLMError as exc:
        yield {"event": "error", "task_id": task_id, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        yield {"event": "error", "task_id": task_id, "error": f"异常分析失败: {exc}"}
