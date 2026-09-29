"""SSE helpers for agent streaming APIs."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from starlette.responses import StreamingResponse


def sse_encode(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def sse_response(events: Iterator[dict[str, Any]]) -> StreamingResponse:
    def _gen() -> Iterator[str]:
        try:
            for item in events:
                event = str(item.get("event") or "message")
                data = {k: v for k, v in item.items() if k != "event"}
                yield sse_encode(event, data)
        except Exception as exc:  # noqa: BLE001
            yield sse_encode("error", {"error": str(exc)})

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
