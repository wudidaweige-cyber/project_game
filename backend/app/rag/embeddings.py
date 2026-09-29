"""OpenAI-compatible embedding client."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import httpx

from app.core.config import Settings, get_settings


class EmbeddingError(RuntimeError):
    pass


class EmbeddingClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def dim(self) -> int:
        return int(self.settings.embedding_dim)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.settings.resolved_embedding_api_key:
            raise EmbeddingError("未配置 EMBEDDING_API_KEY / LLM_API_KEY")

        url = self.settings.resolved_embedding_base_url + "/embeddings"
        # batch to avoid payload limits
        out: list[list[float]] = []
        batch_size = 10
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            payload: dict[str, Any] = {
                "model": self.settings.embedding_model,
                "input": batch,
            }
            headers = {
                "Authorization": f"Bearer {self.settings.resolved_embedding_api_key}",
                "Content-Type": "application/json",
            }
            with httpx.Client(timeout=60.0, trust_env=False) as client:
                resp = client.post(url, headers=headers, json=payload)
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise EmbeddingError(
                        f"Embedding 调用失败: {exc.response.status_code} {exc.response.text[:300]}"
                    ) from exc
                data = resp.json()
            items = data.get("data") or []
            # API may return unsorted; sort by index
            items = sorted(items, key=lambda x: x.get("index", 0))
            for item in items:
                vec = item.get("embedding")
                if not isinstance(vec, list):
                    raise EmbeddingError("Embedding 响应缺少 embedding 字段")
                out.append([float(x) for x in vec])
        if len(out) != len(texts):
            raise EmbeddingError(f"Embedding 数量不匹配: expect {len(texts)} got {len(out)}")
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


@lru_cache
def get_embedding_client() -> EmbeddingClient:
    return EmbeddingClient()
