"""NL2SQL data analysis agent: question → SQL → guard → query → answer."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.agent.llm import LLMError, get_llm_client
from app.agent.schema import SCHEMA_PROMPT
from app.mcp.registry import call_tool
from app.mcp.sql_guard import SqlGuardError, validate_readonly_sql

_SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_BARE_CTE_RE = re.compile(
    r"^\s*([A-Za-z_][\w]*)\s+AS\s*\(",
    re.IGNORECASE,
)
_WORD_WITH_RE = re.compile(r"(?i)(?<![A-Za-z0-9_])WITH(?![A-Za-z0-9_])")
_WORD_SELECT_RE = re.compile(r"(?i)(?<![A-Za-z0-9_])SELECT(?![A-Za-z0-9_])")


def extract_sql(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    m = _SQL_FENCE_RE.search(raw)
    if m:
        raw = m.group(1).strip()

    chosen = ""
    for wm in _WORD_WITH_RE.finditer(raw):
        candidate = raw[wm.start() :]
        if _looks_like_cte(candidate):
            chosen = candidate
            break
    if not chosen:
        select_m = _WORD_SELECT_RE.search(raw)
        if select_m:
            chosen = raw[select_m.start() :]
        else:
            chosen = raw

    raw = chosen
    if ";" in raw:
        parts = [p.strip() for p in raw.split(";") if p.strip()]
        with_parts = [p for p in parts if _looks_like_cte(p)]
        raw = with_parts[0] if with_parts else (parts[0] if parts else raw)

    return repair_sql(raw.strip())


def _looks_like_cte(sql: str) -> bool:
    upper = (sql or "").lstrip().upper()
    if not upper.startswith("WITH"):
        return False
    return bool(re.match(r"WITH\s+[A-Za-z_][\w]*\s+AS\s*\(", upper))


def repair_sql(sql: str) -> str:
    """Fix common model malformations (e.g. CTE missing leading WITH)."""
    text = (sql or "").strip().rstrip(";").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper.startswith("WITH") or upper.startswith("SELECT"):
        return text
    if _BARE_CTE_RE.match(text):
        return f"WITH {text}"
    return text


def check_sql_structure(sql: str) -> str | None:
    """Lightweight structural self-check. Return error message or None if OK."""
    text = (sql or "").strip()
    if not text:
        return "SQL 为空"
    if text.count("(") != text.count(")"):
        return "SQL 括号不配对"
    upper = text.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return "SQL 必须以 SELECT 或 WITH 开头"
    if upper.startswith("WITH") and "SELECT" not in upper:
        return "WITH 查询缺少最终 SELECT"
    # Most analytics queries need FROM; allow trivial SELECT <literal>
    if "FROM" not in upper and not re.match(r"(?i)^SELECT\s+[\d'\"]", text):
        return "SQL 缺少 FROM 子句"
    return None


def _generate_sql(
    question: str,
    *,
    previous_sql: str = "",
    previous_error: str = "",
) -> str:
    llm = get_llm_client()
    user = (
        f"用户问题：{question}\n"
        "请只输出一条 PostgreSQL 只读查询（不要解释、不要 Markdown）。\n"
        "若使用 CTE，必须以 WITH 开头，不要省略 WITH。\n"
        "全站汇总请使用 ops_daily_metric.game_id = ''。"
    )
    if previous_error:
        user += (
            f"\n\n上次生成的 SQL：\n{previous_sql or '(空)'}\n"
            f"校验/执行错误：{previous_error}\n"
            "请修正后重新输出一条完整合法 SQL。"
        )
    content = llm.chat(
        [
            {"role": "system", "content": SCHEMA_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
    )
    return extract_sql(content)


def _validate_candidate(sql: str) -> str:
    struct_err = check_sql_structure(sql)
    if struct_err:
        raise SqlGuardError(struct_err)
    return validate_readonly_sql(sql)


def _generate_and_validate_sql(question: str) -> tuple[str, int, list[str]]:
    """Generate SQL with at most one repair retry. Returns (safe_sql, attempts, errors)."""
    errors: list[str] = []
    sql = _generate_sql(question)
    attempts = 1
    try:
        return _validate_candidate(sql), attempts, errors
    except SqlGuardError as exc:
        errors.append(str(exc))
        sql2 = _generate_sql(question, previous_sql=sql, previous_error=str(exc))
        attempts = 2
        return _validate_candidate(sql2), attempts, errors


_SUMMARIZE_SYSTEM = (
    "你是运营数据分析助手。根据 SQL 查询结果用简洁中文回答用户。"
    "只依据结果，不编造数字；若结果为空请明确说明。"
)


def _summarize_messages(question: str, sql: str, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    preview = rows[:30]
    return [
        {"role": "system", "content": _SUMMARIZE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"问题：{question}\n"
                f"SQL：{sql}\n"
                f"行数：{len(rows)}\n"
                f"结果预览(JSON)：{preview}\n"
                "请给出简明结论。"
            ),
        },
    ]


def _summarize(question: str, sql: str, rows: list[dict[str, Any]]) -> str:
    llm = get_llm_client()
    return llm.chat(_summarize_messages(question, sql, rows), temperature=0.2)


def analyze_question(question: str, max_rows: int = 100) -> dict[str, Any]:
    """Run NL2SQL pipeline. Returns a structured result dict."""
    task_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    base: dict[str, Any] = {
        "ok": False,
        "task_id": task_id,
        "question": question,
        "sql": "",
        "executed_sql": "",
        "row_count": 0,
        "rows": [],
        "answer": "",
        "error": "",
        "sql_attempts": 0,
        "started_at": started.isoformat(),
    }

    q = (question or "").strip()
    if not q:
        base["error"] = "问题为空"
        return base

    try:
        safe_sql, attempts, gen_errors = _generate_and_validate_sql(q)
        base["sql"] = safe_sql
        base["sql_attempts"] = attempts
        base["executed_sql"] = safe_sql

        tool_result = call_tool(
            "run_readonly_sql",
            {"sql": safe_sql, "max_rows": max_rows},
        )
        if not tool_result.get("ok"):
            # One execution retry with DB error feedback
            exec_err = tool_result.get("error") or "查询失败"
            if attempts < 2:
                sql2 = _generate_sql(q, previous_sql=safe_sql, previous_error=exec_err)
                attempts = 2
                base["sql_attempts"] = attempts
                try:
                    safe_sql = _validate_candidate(sql2)
                except SqlGuardError as exc:
                    base["error"] = f"SQL 安全检查拒绝: {exc}"
                    base["sql"] = sql2
                    return base
                base["sql"] = safe_sql
                base["executed_sql"] = safe_sql
                tool_result = call_tool(
                    "run_readonly_sql",
                    {"sql": safe_sql, "max_rows": max_rows},
                )
                if not tool_result.get("ok"):
                    base["error"] = tool_result.get("error") or exec_err
                    if gen_errors:
                        base["error"] = f"{base['error']}（生成阶段曾失败: {gen_errors[-1]}）"
                    return base
            else:
                base["error"] = exec_err
                return base

        data = tool_result.get("data") or {}
        rows = data.get("rows") or []
        base["rows"] = rows
        base["row_count"] = int(data.get("row_count") or len(rows))
        base["answer"] = _summarize(q, safe_sql, rows)
        base["ok"] = True
        return base
    except SqlGuardError as exc:
        base["error"] = f"SQL 安全检查拒绝: {exc}"
        return base
    except LLMError as exc:
        base["error"] = str(exc)
        return base
    except Exception as exc:  # noqa: BLE001
        base["error"] = f"分析失败: {exc}"
        return base


def analyze_question_stream(question: str, max_rows: int = 100):
    """Yield SSE-oriented events for NL2SQL (phase / token / done / error)."""
    task_id = str(uuid.uuid4())
    q = (question or "").strip()
    yield {"event": "meta", "task_id": task_id, "phase": "start", "question": q}

    if not q:
        yield {"event": "error", "task_id": task_id, "error": "问题为空"}
        return

    try:
        yield {"event": "phase", "task_id": task_id, "phase": "generating_sql"}
        try:
            safe_sql, attempts, _ = _generate_and_validate_sql(q)
        except SqlGuardError as exc:
            yield {"event": "error", "task_id": task_id, "error": f"SQL 安全检查拒绝: {exc}"}
            return

        yield {
            "event": "meta",
            "task_id": task_id,
            "phase": "sql_ready",
            "sql": safe_sql,
            "sql_attempts": attempts,
        }

        yield {"event": "phase", "task_id": task_id, "phase": "querying"}
        tool_result = call_tool(
            "run_readonly_sql",
            {"sql": safe_sql, "max_rows": max_rows},
        )
        if not tool_result.get("ok"):
            exec_err = tool_result.get("error") or "查询失败"
            if attempts < 2:
                yield {"event": "phase", "task_id": task_id, "phase": "retrying_sql"}
                sql2 = _generate_sql(q, previous_sql=safe_sql, previous_error=exec_err)
                attempts = 2
                try:
                    safe_sql = _validate_candidate(sql2)
                except SqlGuardError as exc:
                    yield {
                        "event": "error",
                        "task_id": task_id,
                        "error": f"SQL 安全检查拒绝: {exc}",
                        "sql": sql2,
                    }
                    return
                yield {
                    "event": "meta",
                    "task_id": task_id,
                    "phase": "sql_ready",
                    "sql": safe_sql,
                    "sql_attempts": attempts,
                }
                tool_result = call_tool(
                    "run_readonly_sql",
                    {"sql": safe_sql, "max_rows": max_rows},
                )
            if not tool_result.get("ok"):
                yield {
                    "event": "error",
                    "task_id": task_id,
                    "error": tool_result.get("error") or exec_err,
                    "sql": safe_sql,
                }
                return

        data = tool_result.get("data") or {}
        rows = data.get("rows") or []
        row_count = int(data.get("row_count") or len(rows))
        yield {
            "event": "meta",
            "task_id": task_id,
            "phase": "query_done",
            "row_count": row_count,
        }

        yield {"event": "phase", "task_id": task_id, "phase": "answering"}
        llm = get_llm_client()
        answer_parts: list[str] = []
        for piece in llm.chat_stream(_summarize_messages(q, safe_sql, rows), temperature=0.2):
            answer_parts.append(piece)
            yield {"event": "token", "task_id": task_id, "text": piece}

        answer = "".join(answer_parts).strip()
        if not answer:
            yield {"event": "error", "task_id": task_id, "error": "模型未返回有效回答", "sql": safe_sql}
            return

        yield {
            "event": "done",
            "task_id": task_id,
            "question": q,
            "answer": answer,
            "sql": safe_sql,
            "row_count": row_count,
            "rows": rows[:50],
            "sql_attempts": attempts,
        }
    except SqlGuardError as exc:
        yield {"event": "error", "task_id": task_id, "error": f"SQL 安全检查拒绝: {exc}"}
    except LLMError as exc:
        yield {"event": "error", "task_id": task_id, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        yield {"event": "error", "task_id": task_id, "error": f"分析失败: {exc}"}
