"""Knowledge ingest / search / document management HTTP API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.deps import AuthUser, require_roles
from app.core.response import fail, ok
from app.rag.ingest import (
    ALLOWED_DOC_TYPES,
    MAX_UPLOAD_BYTES,
    delete_knowledge_doc,
    get_knowledge_doc,
    ingest_knowledge_dir,
    ingest_markdown_document,
    list_knowledge_docs,
    safe_upload_filename,
)
from app.rag.retriever import search_knowledge

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(5, ge=1, le=20)
    doc_type: str | None = None
    mode: str | None = Field(
        None,
        description="auto|vector|hybrid；默认跟随 RAG_HYBRID_ENABLED",
    )


@router.post("/ingest")
def post_ingest(
    user: Annotated[AuthUser, Depends(require_roles("admin"))],
    reset: bool = Query(False, description="是否重建向量集合"),
) -> dict:
    _ = user
    try:
        result = ingest_knowledge_dir(reset_vectors=reset)
    except Exception as exc:  # noqa: BLE001
        return fail(501, f"ingest failed: {exc}")
    if not result.get("ok"):
        return fail(501, result.get("error") or "ingest failed", result)
    return ok(result)


@router.post("/search")
def post_search(body: SearchRequest) -> dict:
    mode = body.mode if body.mode in ("vector", "hybrid", "auto") else None
    result = search_knowledge(
        body.query,
        top_k=body.top_k,
        doc_type=body.doc_type,
        mode=mode,  # type: ignore[arg-type]
    )
    if not result.get("ok"):
        return fail(501, result.get("error") or "search failed", result)
    return ok(result)


@router.get("/docs")
def get_docs(
    user: Annotated[AuthUser, Depends(require_roles("admin"))],
    doc_type: str | None = Query(None),
) -> dict:
    _ = user
    if doc_type and doc_type not in ALLOWED_DOC_TYPES:
        return fail(400, f"doc_type 无效，允许: {', '.join(sorted(ALLOWED_DOC_TYPES))}")
    return ok(list_knowledge_docs(doc_type=doc_type))


@router.get("/docs/{doc_id}")
def get_doc(
    doc_id: str,
    user: Annotated[AuthUser, Depends(require_roles("admin"))],
) -> dict:
    _ = user
    result = get_knowledge_doc(doc_id, include_chunks=True)
    if not result.get("ok"):
        return fail(404, result.get("error") or "文档不存在")
    return ok(result)


@router.post("/docs")
async def upload_doc(
    user: Annotated[AuthUser, Depends(require_roles("admin"))],
    file: UploadFile = File(..., description="Markdown 文件"),
    doc_type: str | None = Form(None),
) -> dict:
    raw_name = file.filename or "upload.md"
    if not raw_name.lower().endswith(".md"):
        return fail(400, "仅支持 .md 文件")

    data = await file.read()
    if not data:
        return fail(400, "文件为空")
    if len(data) > MAX_UPLOAD_BYTES:
        return fail(400, f"文件过大，上限 {MAX_UPLOAD_BYTES // 1024}KB")

    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        return fail(400, "文件须为 UTF-8 编码的 Markdown")

    settings = get_settings()
    upload_dir = settings.resolved_knowledge_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    fname = safe_upload_filename(raw_name)
    dest = upload_dir / fname
    dest.write_text(content, encoding="utf-8")

    result = ingest_markdown_document(
        filename=fname,
        content=content,
        doc_type=doc_type,
        source_path=str(dest),
        user_id=user.id,
        user_name=user.username,
    )
    if not result.get("ok"):
        return fail(501, result.get("error") or "上传入库失败", result)
    return ok(result)


@router.delete("/docs/{doc_id}")
def remove_doc(
    doc_id: str,
    user: Annotated[AuthUser, Depends(require_roles("admin"))],
) -> dict:
    _ = user
    result = delete_knowledge_doc(doc_id)
    if not result.get("ok"):
        return fail(404, result.get("error") or "文档不存在")
    return ok(result)
