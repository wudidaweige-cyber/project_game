"""Milvus / Milvus Lite vector store for knowledge chunks."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import get_settings


class VectorStoreError(RuntimeError):
    pass


class MilvusVectorStore:
    def __init__(self, uri: str | None = None, collection: str | None = None, token: str | None = None):
        settings = get_settings()
        self.uri = uri or settings.resolved_milvus_uri
        self.collection = collection or settings.milvus_collection
        self.token = settings.milvus_token if token is None else token
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from pymilvus import MilvusClient
            except ImportError as exc:
                raise VectorStoreError("未安装 pymilvus，请 pip install pymilvus") from exc
            kwargs: dict[str, Any] = {"uri": self.uri}
            if self.token:
                kwargs["token"] = self.token
            self._client = MilvusClient(**kwargs)
        return self._client

    def ensure_collection(self, dim: int) -> None:
        from pymilvus import DataType, MilvusClient

        client = self._get_client()
        if client.has_collection(self.collection):
            return

        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("chunk_id", DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field("doc_id", DataType.VARCHAR, max_length=64)
        schema.add_field("doc_type", DataType.VARCHAR, max_length=32)
        schema.add_field("chunk_index", DataType.INT64)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=int(dim))

        index_params = client.prepare_index_params()
        index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")

        client.create_collection(
            collection_name=self.collection,
            schema=schema,
            index_params=index_params,
        )

    def drop_collection(self) -> None:
        client = self._get_client()
        if client.has_collection(self.collection):
            client.drop_collection(self.collection)

    def delete_by_chunk_ids(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        client = self._get_client()
        if not client.has_collection(self.collection):
            return
        quoted = ", ".join([f'"{c}"' for c in chunk_ids])
        client.delete(collection_name=self.collection, filter=f"chunk_id in [{quoted}]")

    def delete_by_doc_ids(self, doc_ids: list[str]) -> None:
        if not doc_ids:
            return
        client = self._get_client()
        if not client.has_collection(self.collection):
            return
        quoted = ", ".join([f'"{d}"' for d in doc_ids])
        try:
            client.delete(collection_name=self.collection, filter=f"doc_id in [{quoted}]")
        except Exception:
            # Lite / older versions may differ; ignore and rely on recreate path
            pass

    def upsert(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        client = self._get_client()
        data = [
            {
                "chunk_id": r["chunk_id"],
                "doc_id": r["doc_id"],
                "doc_type": r["doc_type"],
                "chunk_index": int(r["chunk_index"]),
                "vector": r["embedding"],
            }
            for r in records
        ]
        client.upsert(collection_name=self.collection, data=data)
        return len(data)

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        doc_type: str | None = None,
    ) -> list[dict[str, Any]]:
        client = self._get_client()
        if not client.has_collection(self.collection):
            return []
        try:
            client.load_collection(self.collection)
        except Exception:
            pass
        kwargs: dict[str, Any] = {
            "collection_name": self.collection,
            "data": [query_vector],
            "limit": top_k,
            "output_fields": ["chunk_id", "doc_id", "doc_type", "chunk_index"],
        }
        if doc_type:
            kwargs["filter"] = f'doc_type == "{doc_type}"'
        results = client.search(**kwargs)
        hits = results[0] if results else []
        out: list[dict[str, Any]] = []
        for h in hits:
            entity = h.get("entity") or {}
            out.append(
                {
                    "chunk_id": entity.get("chunk_id") or h.get("id"),
                    "doc_id": entity.get("doc_id"),
                    "doc_type": entity.get("doc_type"),
                    "chunk_index": entity.get("chunk_index"),
                    "score": h.get("distance"),
                }
            )
        return out

    def count(self) -> int:
        client = self._get_client()
        if not client.has_collection(self.collection):
            return 0
        try:
            stats = client.get_collection_stats(self.collection)
            if isinstance(stats, dict):
                return int(stats.get("row_count") or stats.get("rowCount") or 0)
        except Exception:
            pass
        # fallback
        try:
            rows = client.query(collection_name=self.collection, filter="", output_fields=["chunk_id"], limit=16384)
            return len(rows or [])
        except Exception:
            return 0


@lru_cache
def get_vector_store() -> MilvusVectorStore:
    return MilvusVectorStore()
