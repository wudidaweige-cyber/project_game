"""Job queue for Supervisor tasks: Redis if configured, else in-process."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from queue import Empty, Queue
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

QUEUE_KEY = "game-ops:agent:jobs"

_memory_queue: Queue[str] = Queue(maxsize=200)
_stop = threading.Event()
_worker_started = False
_worker_lock = threading.Lock()


class QueueError(RuntimeError):
    pass


def _normalized_redis_url() -> str | None:
    """Return a usable Redis URL, or None to use in-process memory queue."""
    url = (get_settings().redis_url or "").strip()
    if not url:
        return None
    if url.startswith(("redis://", "rediss://", "unix://")):
        return url
    logger.warning(
        "Invalid REDIS_URL %r (need redis:// / rediss:// / unix://); using memory queue",
        url,
    )
    return None


def queue_backend() -> str:
    return "redis" if _normalized_redis_url() else "memory"


def ping_queue() -> dict[str, Any]:
    backend = queue_backend()
    if backend == "memory":
        return {"ok": True, "backend": "memory", "queued": _memory_queue.qsize()}
    try:
        client = _redis_client()
        client.ping()
        return {
            "ok": True,
            "backend": "redis",
            "queued": int(client.llen(QUEUE_KEY)),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "backend": "redis", "error": str(exc)}


def enqueue_job(job: dict[str, Any]) -> None:
    payload = json.dumps(job, ensure_ascii=False)
    if queue_backend() == "redis":
        try:
            _redis_client().lpush(QUEUE_KEY, payload)
            return
        except Exception as exc:  # noqa: BLE001
            raise QueueError(f"Redis 入队失败: {exc}") from exc
    try:
        _memory_queue.put(payload, timeout=2)
    except Exception as exc:  # noqa: BLE001
        raise QueueError(f"内存队列已满或入队失败: {exc}") from exc


def dequeue_job(*, timeout: float = 1.0) -> dict[str, Any] | None:
    if _stop.is_set():
        return None
    if queue_backend() == "redis":
        try:
            item = _redis_client().brpop(QUEUE_KEY, timeout=max(1, int(timeout)))
            if not item:
                return None
            raw = item[1]
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis dequeue failed: %s", exc)
            return None
    try:
        raw = _memory_queue.get(timeout=timeout)
        return json.loads(raw)
    except Empty:
        return None


def process_job(job: dict[str, Any]) -> dict[str, Any]:
    """Run one Supervisor job and persist onto the pre-created task."""
    from app.agent.supervisor import run_supervisor
    from app.api.v1.agent_api import persist_supervisor_result

    task_id = job["task_id"]
    session_id = job["session_id"]
    question = job["question"]
    from app.services import ai_trace

    try:
        ai_trace.mark_task_running(task_id)
        result = run_supervisor(
            question,
            max_rows=int(job.get("max_rows") or 100),
            top_k=int(job.get("top_k") or 5),
        )
        return persist_supervisor_result(
            session_id=session_id,
            question=question,
            result=result,
            task_id=task_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent job failed task_id=%s", task_id)
        ai_trace.finish_task(
            task_id=task_id,
            status="failed",
            error_message=str(exc),
        )
        raise


def worker_loop(process: Callable[[dict[str, Any]], Any] | None = None) -> None:
    handler = process or process_job
    logger.info("agent queue worker started backend=%s", queue_backend())
    while not _stop.is_set():
        job = dequeue_job(timeout=1.0)
        if not job:
            continue
        try:
            handler(job)
        except Exception:  # noqa: BLE001
            continue
    logger.info("agent queue worker stopped")


def start_worker_thread() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _stop.clear()
        thread = threading.Thread(target=worker_loop, name="agent-queue-worker", daemon=True)
        thread.start()
        _worker_started = True


def stop_worker() -> None:
    _stop.set()


def _redis_client():
    import redis

    url = _normalized_redis_url()
    if not url:
        raise QueueError("REDIS_URL 未配置或格式无效")
    return redis.Redis.from_url(url, decode_responses=True)
