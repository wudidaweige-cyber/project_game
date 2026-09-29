"""Knowledge Q&A agent: retrieve → grounded answer (no fabrication)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.agent.llm import LLMError, get_llm_client
from app.rag.retriever import search_knowledge

SYSTEM_PROMPT = """你是游戏账号租赁平台的运营知识助手。
只能依据检索到的知识片段回答，不得编造规则或流程。
要求：
1. 用简洁中文回答。
2. 关键结论标注来源编号，如 [1]、[2]，编号对应检索片段。
3. 若片段不足以回答，或片段主题与问题明显不符（虚构场景/其他行业/知识库未覆盖），明确说明「无知识依据」，不要把通用规则硬套到无关问题上。
4. 不要输出与问题无关的内容。
""".strip()


def _format_context(hits: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for i, h in enumerate(hits, start=1):
        title = h.get("title") or "未命名文档"
        doc_type = h.get("doc_type") or ""
        content = (h.get("content") or "").strip()
        blocks.append(f"[{i}] 《{title}》（类型:{doc_type}）\n{content}")
    return "\n\n".join(blocks)


def _citations(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i, h in enumerate(hits, start=1):
        out.append(
            {
                "index": i,
                "chunk_id": h.get("chunk_id"),
                "doc_id": h.get("doc_id"),
                "doc_type": h.get("doc_type"),
                "title": h.get("title") or "",
                "source_path": h.get("source_path") or "",
                "score": h.get("score"),
                "snippet": (h.get("content") or "")[:240],
            }
        )
    return out


def answer_knowledge_question(
    question: str,
    *,
    top_k: int = 5,
    doc_type: str | None = None,
) -> dict[str, Any]:
    task_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    base: dict[str, Any] = {
        "ok": False,
        "task_id": task_id,
        "question": question,
        "answer": "",
        "citations": [],
        "hit_count": 0,
        "no_hit": False,
        "error": "",
        "started_at": started.isoformat(),
    }

    q = (question or "").strip()
    if not q:
        base["error"] = "问题为空"
        return base

    try:
        retrieved = search_knowledge(q, top_k=top_k, doc_type=doc_type)
        if not retrieved.get("ok"):
            base["error"] = retrieved.get("error") or "检索失败"
            return base

        hits = retrieved.get("hits") or []
        base["hit_count"] = len(hits)
        base["citations"] = _citations(hits)

        if not hits:
            base["ok"] = True
            base["no_hit"] = True
            base["answer"] = (
                "知识库中未检索到相关依据，无法回答该问题。"
                "请换个问法，或确认相关 SOP/规则文档已入库。"
            )
            return base

        context = _format_context(hits)
        llm = get_llm_client()
        answer = llm.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"用户问题：{q}\n\n"
                        f"检索片段：\n{context}\n\n"
                        "请基于上述片段作答，并标注来源编号。"
                    ),
                },
            ],
            temperature=0.2,
        )
        base["answer"] = (answer or "").strip()
        if not base["answer"]:
            base["error"] = "模型未返回有效回答"
            return base
        base["ok"] = True
        return base
    except LLMError as exc:
        base["error"] = str(exc)
        return base
    except Exception as exc:  # noqa: BLE001
        base["error"] = f"知识问答失败: {exc}"
        return base


_NO_HIT_ANSWER = (
    "知识库中未检索到相关依据，无法回答该问题。"
    "请换个问法，或确认相关 SOP/规则文档已入库。"
)


def _answer_messages(question: str, context: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"用户问题：{question}\n\n"
                f"检索片段：\n{context}\n\n"
                "请基于上述片段作答，并标注来源编号。"
            ),
        },
    ]


def answer_knowledge_question_stream(
    question: str,
    *,
    top_k: int = 5,
    doc_type: str | None = None,
):
    """Yield SSE-oriented events for knowledge Q&A."""
    task_id = str(uuid.uuid4())
    q = (question or "").strip()
    yield {"event": "meta", "task_id": task_id, "phase": "start", "question": q}

    if not q:
        yield {"event": "error", "task_id": task_id, "error": "问题为空"}
        return

    try:
        yield {"event": "phase", "task_id": task_id, "phase": "retrieving"}
        retrieved = search_knowledge(q, top_k=top_k, doc_type=doc_type)
        if not retrieved.get("ok"):
            yield {
                "event": "error",
                "task_id": task_id,
                "error": retrieved.get("error") or "检索失败",
            }
            return

        hits = retrieved.get("hits") or []
        citations = _citations(hits)
        yield {
            "event": "meta",
            "task_id": task_id,
            "phase": "retrieved",
            "hit_count": len(hits),
            "citations": citations,
            "no_hit": not bool(hits),
        }

        if not hits:
            for piece in _NO_HIT_ANSWER:
                yield {"event": "token", "task_id": task_id, "text": piece}
            yield {
                "event": "done",
                "task_id": task_id,
                "question": q,
                "answer": _NO_HIT_ANSWER,
                "citations": [],
                "hit_count": 0,
                "no_hit": True,
            }
            return

        yield {"event": "phase", "task_id": task_id, "phase": "answering"}
        context = _format_context(hits)
        llm = get_llm_client()
        parts: list[str] = []
        for piece in llm.chat_stream(_answer_messages(q, context), temperature=0.2):
            parts.append(piece)
            yield {"event": "token", "task_id": task_id, "text": piece}

        answer = "".join(parts).strip()
        if not answer:
            yield {"event": "error", "task_id": task_id, "error": "模型未返回有效回答"}
            return

        yield {
            "event": "done",
            "task_id": task_id,
            "question": q,
            "answer": answer,
            "citations": citations,
            "hit_count": len(hits),
            "no_hit": False,
        }
    except LLMError as exc:
        yield {"event": "error", "task_id": task_id, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        yield {"event": "error", "task_id": task_id, "error": f"知识问答失败: {exc}"}