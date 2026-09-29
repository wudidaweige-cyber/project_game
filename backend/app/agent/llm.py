"""OpenAI-compatible chat client for agents."""

from __future__ import annotations

import json
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import Settings, get_settings


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }

    def _url(self) -> str:
        return self.settings.llm_base_url.rstrip("/") + "/chat/completions"

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        if not self.settings.llm_api_key:
            raise LLMError("未配置 LLM_API_KEY")

        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": temperature,
        }
        timeout = float(self.settings.agent_timeout_seconds)
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(self._url(), headers=self._headers(), json=payload)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise LLMError(
                    f"LLM 调用失败: {exc.response.status_code} {exc.response.text[:300]}"
                ) from exc
            data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise LLMError(f"LLM 响应无法解析: {data}") from exc

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> Iterator[str]:
        """Yield text deltas from an OpenAI-compatible streaming completion."""
        if not self.settings.llm_api_key:
            raise LLMError("未配置 LLM_API_KEY")

        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        timeout = float(self.settings.agent_timeout_seconds)
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            with client.stream(
                "POST",
                self._url(),
                headers=self._headers(),
                json=payload,
            ) as resp:
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    body = exc.response.read().decode("utf-8", errors="replace")[:300]
                    raise LLMError(f"LLM 流式调用失败: {exc.response.status_code} {body}") from exc

                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    try:
                        delta = chunk["choices"][0].get("delta") or {}
                        piece = delta.get("content") or ""
                    except (KeyError, IndexError, TypeError, AttributeError):
                        continue
                    if piece:
                        yield piece


@lru_cache
def get_llm_client() -> LLMClient:
    return LLMClient()
