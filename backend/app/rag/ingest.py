"""Ingest markdown knowledge files → PostgreSQL + vector store."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db import get_engine
from app.models import OpsKnowledgeChunk, OpsKnowledgeDoc
from app.rag.chunker import chunk_markdown, infer_doc_type, infer_title
from app.rag.embeddings import get_embedding_client
from app.rag.vector_store import get_vector_store

ALLOWED_DOC_TYPES = frozenset({"sop", "refund", "account", "pricing", "risk", "other"})
MAX_UPLOAD_BYTES = 512 * 1024
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\u4e00-\u9fff\-]+")


def _session() -> Session:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)()


def _audit(user_id: str = "rag", user_name: str = "rag-ingest") -> dict[str, str]:
    return {
        "create_user_id": user_id,
        "create_user_name": user_name,
        "update_user_id": user_id,
        "update_user_name": user_name,
    }


def _rebuild_bm25() -> tuple[int, str]:
    try:
        from app.rag.bm25_index import rebuild_bm25_from_db

        return rebuild_bm25_from_db(), ""
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def safe_upload_filename(filename: str) -> str:
    name = Path(filename or "upload.md").name
    if not name.lower().endswith(".md"):
        name = f"{name}.md"
    stem = Path(name).stem
    cleaned = _SAFE_NAME_RE.sub("_", stem).strip("._") or "upload"
    return f"{cleaned[:80]}.md"


def normalize_doc_type(doc_type: str | None, filename: str) -> str:
    raw = (doc_type or "").strip().lower()
    if raw in ALLOWED_DOC_TYPES:
        return raw
    inferred = infer_doc_type(filename)
    return inferred if inferred in ALLOWED_DOC_TYPES else "other"


def _purge_doc(session: Session, store: Any, doc: OpsKnowledgeDoc) -> list[str]:
    old_chunks = (
        session.execute(select(OpsKnowledgeChunk).where(OpsKnowledgeChunk.doc_id == doc.id))
        .scalars()
        .all()
    )
    old_ids = [c.id for c in old_chunks]
    if old_ids:
        store.delete_by_chunk_ids(old_ids)
    session.execute(delete(OpsKnowledgeChunk).where(OpsKnowledgeChunk.doc_id == doc.id))
    session.delete(doc)
    session.flush()
    return old_ids


def _doc_summary(doc: OpsKnowledgeDoc, chunk_count: int | None = None) -> dict[str, Any]:
    return {
        "id": doc.id,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "source_path": doc.source_path,
        "status": doc.status,
        "embed_status": doc.embed_status,
        "chunk_count": chunk_count,
        "create_time": doc.create_time.isoformat() if doc.create_time else None,
        "update_time": doc.update_time.isoformat() if doc.update_time else None,
    }


def ingest_markdown_document(
    *,
    filename: str,
    content: str,
    doc_type: str | None = None,
    source_path: str | None = None,
    user_id: str = "rag",
    user_name: str = "rag-ingest",
    rebuild_bm25: bool = True,
) -> dict[str, Any]:
    """Chunk + embed one markdown document into PG and Milvus."""
    text = (content or "").strip()
    if not text:
        return {"ok": False, "error": "文档内容为空"}

    settings = get_settings()
    fname = safe_upload_filename(filename)
    resolved_type = normalize_doc_type(doc_type, fname)
    title = infer_title(text, Path(fname).stem)
    pieces = chunk_markdown(text)
    if not pieces:
        return {"ok": False, "error": "切分后无有效切片"}

    src = source_path or fname
    embedder = get_embedding_client()
    store = get_vector_store()
    dim = embedder.dim
    store.ensure_collection(dim)
    audit = _audit(user_id, user_name)

    with _session() as session:
        existing = session.execute(
            select(OpsKnowledgeDoc).where(OpsKnowledgeDoc.source_path == src)
        ).scalar_one_or_none()
        if existing:
            _purge_doc(session, store, existing)

        doc_id = str(uuid.uuid4())
        doc = OpsKnowledgeDoc(
            id=doc_id,
            title=title,
            doc_type=resolved_type,
            source_path=src,
            status="published",
            embed_status="running",
            **audit,
        )
        session.add(doc)
        session.flush()

        try:
            texts = [p["content"] for p in pieces]
            vectors = embedder.embed_documents(texts)
            if vectors and len(vectors[0]) != dim:
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
                        doc_type=resolved_type,
                        chunk_index=int(piece["chunk_index"]),
                        content=piece["content"],
                        token_count=int(piece["token_count"]),
                        milvus_collection=settings.milvus_collection,
                        **audit,
                    )
                )
                records.append(
                    {
                        "chunk_id": chunk_id,
                        "doc_id": doc_id,
                        "doc_type": resolved_type,
                        "chunk_index": int(piece["chunk_index"]),
                        "embedding": vec,
                    }
                )

            store.upsert(records)
            doc.embed_status = "success"
            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            return {"ok": False, "error": f"向量化入库失败: {exc}"}

    out: dict[str, Any] = {
        "ok": True,
        "error": "",
        "document": {
            "id": doc_id,
            "title": title,
            "doc_type": resolved_type,
            "source_path": src,
            "status": "published",
            "embed_status": "success",
            "chunk_count": len(pieces),
        },
        "chunk_count": len(pieces),
        "vector_count": store.count(),
    }
    if rebuild_bm25:
        bm25_count, bm25_warning = _rebuild_bm25()
        out["bm25_count"] = bm25_count
        if bm25_warning:
            out["bm25_warning"] = bm25_warning
    return out


def list_knowledge_docs(*, doc_type: str | None = None) -> dict[str, Any]:
    with _session() as session:
        stmt = select(OpsKnowledgeDoc).order_by(OpsKnowledgeDoc.update_time.desc())
        if doc_type:
            stmt = stmt.where(OpsKnowledgeDoc.doc_type == doc_type)
        docs = session.execute(stmt).scalars().all()
        counts = dict(
            session.execute(
                select(OpsKnowledgeChunk.doc_id, func.count())
                .group_by(OpsKnowledgeChunk.doc_id)
            ).all()
        )
        items = [_doc_summary(d, int(counts.get(d.id, 0))) for d in docs]
    return {"ok": True, "items": items, "total": len(items)}


def get_knowledge_doc(doc_id: str, *, include_chunks: bool = True) -> dict[str, Any]:
    with _session() as session:
        doc = session.get(OpsKnowledgeDoc, doc_id)
        if not doc:
            return {"ok": False, "error": "文档不存在"}
        chunks: list[dict[str, Any]] = []
        if include_chunks:
            rows = (
                session.execute(
                    select(OpsKnowledgeChunk)
                    .where(OpsKnowledgeChunk.doc_id == doc_id)
                    .order_by(OpsKnowledgeChunk.chunk_index.asc())
                )
                .scalars()
                .all()
            )
            chunks = [
                {
                    "id": c.id,
                    "chunk_index": c.chunk_index,
                    "content": c.content,
                    "token_count": c.token_count,
                }
                for c in rows
            ]
        summary = _doc_summary(doc, len(chunks) if include_chunks else None)
    return {"ok": True, "document": summary, "chunks": chunks}


def delete_knowledge_doc(doc_id: str) -> dict[str, Any]:
    store = get_vector_store()
    with _session() as session:
        doc = session.get(OpsKnowledgeDoc, doc_id)
        if not doc:
            return {"ok": False, "error": "文档不存在"}
        title = doc.title
        _purge_doc(session, store, doc)
        session.commit()
    bm25_count, bm25_warning = _rebuild_bm25()
    out: dict[str, Any] = {
        "ok": True,
        "deleted_id": doc_id,
        "title": title,
        "bm25_count": bm25_count,
    }
    if bm25_warning:
        out["bm25_warning"] = bm25_warning
    return out


def ingest_knowledge_dir(knowledge_dir: Path | None = None, *, reset_vectors: bool = False) -> dict[str, Any]:
    settings = get_settings()
    root = Path(knowledge_dir) if knowledge_dir else settings.resolved_knowledge_dir
    if not root.exists():
        return {"ok": False, "error": f"知识目录不存在: {root}", "doc_count": 0, "chunk_count": 0}

    files = sorted([p for p in root.glob("*.md") if p.name.lower() != "readme.md"])
    # also include uploads subfolder
    upload_dir = root / "uploads"
    if upload_dir.is_dir():
        files.extend(sorted([p for p in upload_dir.glob("*.md") if p.name.lower() != "readme.md"]))

    if not files:
        return {"ok": False, "error": "未找到可入库的 .md 文件", "doc_count": 0, "chunk_count": 0}

    store = get_vector_store()
    embedder = get_embedding_client()
    dim = embedder.dim
    if reset_vectors:
        store.drop_collection()
    store.ensure_collection(dim)

    total_chunks = 0
    doc_summaries: list[dict[str, Any]] = []
    errors: list[str] = []

    for path in files:
        content = path.read_text(encoding="utf-8")
        result = ingest_markdown_document(
            filename=path.name,
            content=content,
            source_path=str(path),
            rebuild_bm25=False,
        )
        if not result.get("ok"):
            errors.append(f"{path.name}: {result.get('error')}")
            continue
        doc = result["document"]
        total_chunks += int(result.get("chunk_count") or 0)
        doc_summaries.append(
            {
                "doc_id": doc["id"],
                "title": doc["title"],
                "doc_type": doc["doc_type"],
                "path": path.name,
                "chunks": doc["chunk_count"],
            }
        )

    bm25_count, bm25_warning = _rebuild_bm25()
    if not doc_summaries and errors:
        return {
            "ok": False,
            "error": "; ".join(errors[:3]),
            "doc_count": 0,
            "chunk_count": 0,
        }

    out: dict[str, Any] = {
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
    if bm25_warning:
        out["bm25_warning"] = bm25_warning
    if errors:
        out["partial_errors"] = errors
    return out
