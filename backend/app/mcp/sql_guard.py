"""Readonly SQL validation for AI / MCP paths."""

from __future__ import annotations

import re

FORBIDDEN_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "REPLACE",
    "GRANT",
    "REVOKE",
    "MERGE",
    "CALL",
    "EXEC",
    "EXECUTE",
    "COPY",
    "VACUUM",
    "INTO",  # blocks SELECT INTO / INSERT INTO patterns when combined carefully
)

# Allow "INTO" only if we handle carefully - actually SELECT INTO is write-ish in some DBs.
# Better: strip comments, require startswith SELECT, no semicolon mid-query, check forbidden as whole words.


class SqlGuardError(ValueError):
    pass


_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"--.*?$", re.MULTILINE)
_WORD_RE = re.compile(r"\b([A-Za-z_]+)\b")


def _normalize(sql: str) -> str:
    text = sql.strip()
    text = _COMMENT_RE.sub(" ", text)
    text = _LINE_COMMENT_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def validate_readonly_sql(sql: str) -> str:
    """Return cleaned SQL if safe; raise SqlGuardError otherwise."""
    if not sql or not str(sql).strip():
        raise SqlGuardError("SQL 为空")

    cleaned = _normalize(sql)
    if ";" in cleaned.rstrip(";"):
        raise SqlGuardError("拒绝多语句 SQL")

    cleaned = cleaned.rstrip(";").strip()
    upper = cleaned.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise SqlGuardError("仅允许 SELECT / WITH 只读查询")

    words = {m.group(1).upper() for m in _WORD_RE.finditer(cleaned)}
    # INTO after SELECT is dangerous (SELECT INTO); block INTO keyword entirely for MVP
    blocked = words.intersection(FORBIDDEN_KEYWORDS)
    # WITH ... SELECT is ok; but INSERT etc caught above
    if blocked:
        raise SqlGuardError(f"拒绝危险关键字: {', '.join(sorted(blocked))}")

    return cleaned
