"""Knowledge ingest / search HTTP API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.deps import AuthUser, require_roles
from app.core.response import fail, ok
from app.rag.ingest import ingest_knowledge_dir
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
    result = ingest_knowledge_dir(reset_vectors=reset)
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
