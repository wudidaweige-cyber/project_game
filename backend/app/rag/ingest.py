"""Ingest markdown knowledge files → PostgreSQL + vector store."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db import get_engine
from app.models import OpsKnowledgeChunk, OpsKnowledgeDoc
from app.rag.chunker import chunk_markdown, infer_doc_type, infer_title
from app.rag.embeddings import get_embedding_client
from app.rag.vector_store import get_vector_store


def _session() -> Session:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)()


def _audit() -> dict[str, str]:
    return {
        "create_user_id": "rag",
        "create_user_name": "rag-ingest",
        "update_user_id": "rag",
        "update_user_name": "rag-ingest",
    }


def ingest_knowledge_dir(knowledge_dir: Path | None = None, *, reset_vectors: bool = False) -> dict[str, Any]:
    settings = get_settings()
    root = Path(knowledge_dir) if knowledge_dir else settings.resolved_knowledge_dir
    if not root.exists():
        return {"ok": False, "error": f"知识目录不存在: {root}", "doc_count": 0, "chunk_count": 0}

    files = sorted([p for p in root.glob("*.md") if p.name.lower() != "readme.md"])
    if not files:
        return {"ok": False, "error": "未找到可入库的 .md 文件", "doc_count": 0, "chunk_count": 0}

    embedder = get_embedding_client()
    store = get_vector_store()

    # detect dim from settings; will validate with first batch
    dim = embedder.dim
    if reset_vectors:
        store.drop_collection()
    store.ensure_collection(dim)

    total_chunks = 0
    doc_summaries: list[dict[str, Any]] = []

    with _session() as session:
        for path in files:
            content = path.read_text(encoding="utf-8")
            doc_type = infer_doc_type(path.name)
            title = infer_title(content, path.stem)
            pieces = chunk_markdown(content)
            if not pieces:
                continue

            # replace existing doc with same source_path
            existing = session.execute(
                select(OpsKnowledgeDoc).where(OpsKnowledgeDoc.source_path == str(path))
            ).scalar_one_or_none()
            if existing:
                old_chunks = session.execute(
                    select(OpsKnowledgeChunk).where(OpsKnowledgeChunk.doc_id == existing.id)
                ).scalars().all()
                old_ids = [c.id for c in old_chunks]
                store.delete_by_chunk_ids(old_ids)
                session.execute(delete(OpsKnowledgeChunk).where(OpsKnowledgeChunk.doc_id == existing.id))
                session.delete(existing)
                session.flush()

            doc_id = str(uuid.uuid4())
            doc = OpsKnowledgeDoc(
                id=doc_id,
                title=title,
                doc_type=doc_type,
                source_path=str(path),
                status="published",
                embed_status="running",
                **_audit(),
            )
            session.add(doc)
            session.flush()

            texts = [p["content"] for p in pieces]
            vectors = embedder.embed_documents(texts)
            if vectors and len(vectors[0]) != dim:
                # adapt collection if provider dim differs
                dim = len(vectors[0])
                store.drop_collection()
                store.ensure_collection(dim)

            records: list[dict[str, Any]] = []
            for piece, vec in zip(pieces, vectors, strict=True):
                chunk_id = str(uuid.uuid4())
                session.add(
                    OpsKnowledgeChunk(
                        id=chunk_id,
                        doc_id=doc_id,
                        doc_type=doc_type,
                        chunk_index=int(piece["chunk_index"]),
                        content=piece["content"],
                        token_count=int(piece["token_count"]),
                        milvus_collection=settings.milvus_collection,
                        **_audit(),
                    )
                )
                records.append(
                    {
                        "chunk_id": chunk_id,
                        "doc_id": doc_id,
                        "doc_type": doc_type,
                        "chunk_index": int(piece["chunk_index"]),
                        "embedding": vec,
                    }
                )

            store.upsert(records)
            doc.embed_status = "success"
            total_chunks += len(records)
            doc_summaries.append(
                {
                    "doc_id": doc_id,
                    "title": title,
                    "doc_type": doc_type,
                    "path": path.name,
                    "chunks": len(records),
                }
            )

        session.commit()

    # Keep sparse index in sync for hybrid retrieval
    bm25_count = 0
    try:
        from app.rag.bm25_index import rebuild_bm25_from_db

        bm25_count = rebuild_bm25_from_db()
    except Exception as exc:  # noqa: BLE001
        # ingest still succeeds; hybrid falls back / rebuilds lazily
        return {
            "ok": True,
            "error": "",
            "knowledge_dir": str(root),
            "milvus_uri": settings.resolved_milvus_uri,
            "collection": settings.milvus_collection,
            "embedding_model": settings.embedding_model,
            "embedding_dim": dim,
            "doc_count": len(doc_summaries),
            "chunk_count": total_chunks,
            "documents": doc_summaries,
            "vector_count": store.count(),
            "bm25_count": 0,
            "bm25_warning": str(exc),
        }

    return {
        "ok": True,
        "error": "",
        "knowledge_dir": str(root),
        "milvus_uri": settings.resolved_milvus_uri,
        "collection": settings.milvus_collection,
        "embedding_model": settings.embedding_model,
        "embedding_dim": dim,
        "doc_count": len(doc_summaries),
        "chunk_count": total_chunks,
        "documents": doc_summaries,
        "vector_count": store.count(),
        "bm25_count": bm25_count,
    }
