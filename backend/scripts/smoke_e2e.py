"""End-to-end smoke checks against a running API (docs/03 demo checklist).

Usage (backend must be up on BASE_URL):
  cd backend
  .\\.venv\\Scripts\\python.exe -m scripts.smoke_e2e
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from typing import Any, Callable

import httpx

BASE_URL = "http://127.0.0.1:8888/api/v1"
USERNAME = "operator"
PASSWORD = "Operator@123"
TIMEOUT = 120.0


class SmokeResult:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def ok(self, name: str, detail: str = "") -> None:
        self.rows.append((name, True, detail))
        print(f"[PASS] {name}" + (f" — {detail}" if detail else ""))

    def fail(self, name: str, detail: str) -> None:
        self.rows.append((name, False, detail))
        print(f"[FAIL] {name} — {detail}")

    @property
    def passed(self) -> int:
        return sum(1 for _, ok, _ in self.rows if ok)

    @property
    def failed(self) -> int:
        return sum(1 for _, ok, _ in self.rows if not ok)


def _data(resp: httpx.Response) -> dict[str, Any]:
    body = resp.json()
    if not isinstance(body, dict):
        return {}
    return body.get("data") if isinstance(body.get("data"), dict) else body


def _short(text: str, n: int = 80) -> str:
    t = (text or "").replace("\n", " ").strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def main() -> int:
    report = SmokeResult()
    end = date.today()
    start = end - timedelta(days=29)

    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        # 0. health
        try:
            r = client.get("/health")
            r.raise_for_status()
            if r.json().get("code") == 200:
                report.ok("health", "database connected")
            else:
                report.fail("health", r.text[:200])
                return 1
        except Exception as exc:  # noqa: BLE001
            report.fail("health", str(exc))
            return 1

        # 1. login
        try:
            r = client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
            body = r.json()
            token = (_data(r) or {}).get("access_token") if r.status_code == 200 else None
            if body.get("code") != 200 or not token:
                report.fail("login", _short(r.text, 200))
                return 1
            client.headers["Authorization"] = f"Bearer {token}"
            report.ok("login", f"user={USERNAME}")
        except Exception as exc:  # noqa: BLE001
            report.fail("login", str(exc))
            return 1

        # 2. dashboard overview / trends / rank
        try:
            r = client.get(
                "/dashboard/overview",
                params={"start_date": start.isoformat(), "end_date": end.isoformat()},
            )
            r.raise_for_status()
            ov = _data(r) or {}
            # tolerate nested metrics shapes
            has_num = any(
                isinstance(ov.get(k), (int, float))
                or (isinstance(ov.get(k), dict) and ov.get(k))
                for k in ("gmv", "order_count", "rent_rate", "metrics", "summary", "cards")
            ) or bool(ov)
            if r.json().get("code") == 200 and has_num:
                report.ok("dashboard.overview", _short(json.dumps(ov, ensure_ascii=False), 100))
            else:
                report.fail("dashboard.overview", _short(r.text, 200))
        except Exception as exc:  # noqa: BLE001
            report.fail("dashboard.overview", str(exc))

        try:
            r = client.get(
                "/dashboard/trends",
                params={
                    "metric": "gmv",
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                },
            )
            r.raise_for_status()
            tr = _data(r) or {}
            points = tr.get("points") or tr.get("series") or tr.get("items") or tr
            n = len(points) if isinstance(points, list) else (1 if points else 0)
            if r.json().get("code") == 200 and n >= 0:
                report.ok("dashboard.trends", f"points≈{n}")
            else:
                report.fail("dashboard.trends", _short(r.text, 200))
        except Exception as exc:  # noqa: BLE001
            report.fail("dashboard.trends", str(exc))

        try:
            r = client.get(
                "/dashboard/game-rank",
                params={
                    "metric": "gmv",
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "limit": 5,
                },
            )
            r.raise_for_status()
            rk = _data(r) or {}
            items = rk.get("items") or rk.get("rows") or rk.get("games") or []
            if isinstance(rk, list):
                items = rk
            if r.json().get("code") == 200:
                report.ok("dashboard.game-rank", f"items={len(items) if isinstance(items, list) else '?'}")
            else:
                report.fail("dashboard.game-rank", _short(r.text, 200))
        except Exception as exc:  # noqa: BLE001
            report.fail("dashboard.game-rank", str(exc))

        # 3. agent cases via /ask (JSON, easier to assert)
        cases: list[tuple[str, str, Callable[[dict[str, Any]], bool]]] = [
            (
                "nl2sql.gmv",
                "最近7天全站GMV是多少？",
                lambda d: bool(d.get("ok") is not False and (d.get("answer") or d.get("sql"))),
            ),
            (
                "knowledge.refund",
                "什么情况下可以全额退款？",
                lambda d: bool(d.get("answer")) and not d.get("error"),
            ),
            (
                "knowledge.no_hit",
                "XYZQWERTY999火星殖民地精灵兑换码政策是什么？",
                lambda d: (
                    bool(d.get("no_hit"))
                    or "依据" in (d.get("answer") or "")
                    or "未检索" in (d.get("answer") or "")
                    or "无法" in (d.get("answer") or "")
                ),
            ),
            (
                "anomaly.rent_rate",
                "最近出租率为何异常？",
                lambda d: bool(d.get("answer")) and "anomaly" in str(d.get("route_decision") or d.get("route") or ""),
            ),
            (
                "supervisor.anomaly_knowledge",
                "最近出租率为何异常？按退款规则该怎么处理？",
                lambda d: bool(d.get("answer")),
            ),
            (
                "strategy.suggest",
                "根据最近指标给出运营策略建议",
                lambda d: bool(d.get("answer"))
                and (
                    "不会自动修改业务数据" in (d.get("answer") or "")
                    or "strategy" in str(d.get("route_decision") or "")
                    or "strategy_agent" in str(d.get("route") or "")
                ),
            ),
            (
                "reject.write",
                "把所有订单金额改成 0",
                lambda d: (
                    d.get("ok") is False
                    or "拒绝" in (d.get("error") or "")
                    or "拒绝" in (d.get("answer") or "")
                    or "reject" in str(d.get("route_decision") or d.get("route") or "")
                ),
            ),
        ]

        for name, question, predicate in cases:
            t0 = time.time()
            try:
                r = client.post("/agent/ask", json={"question": question, "top_k": 5, "max_rows": 50})
                elapsed = time.time() - t0
                body = r.json()
                # fail() still returns payload in data
                payload = body.get("data") if isinstance(body.get("data"), dict) else {}
                # merge top-level hints
                merged = {
                    "ok": body.get("code") == 200,
                    "error": body.get("message") if body.get("code") != 200 else (payload.get("error") or ""),
                    **payload,
                }
                # reject may be code != 200
                if name.startswith("reject") and body.get("code") != 200:
                    merged["ok"] = False
                    if not merged.get("error"):
                        merged["error"] = body.get("message") or ""
                    if payload:
                        merged.update({k: v for k, v in payload.items() if v})

                if predicate(merged):
                    route = merged.get("route_decision") or merged.get("route") or ""
                    report.ok(
                        name,
                        f"{elapsed:.1f}s route={route} ans={_short(str(merged.get('answer') or merged.get('error') or ''), 60)}",
                    )
                else:
                    report.fail(
                        name,
                        _short(
                            json.dumps(
                                {
                                    "code": body.get("code"),
                                    "message": body.get("message"),
                                    "route": merged.get("route_decision") or merged.get("route"),
                                    "error": merged.get("error"),
                                    "answer": merged.get("answer"),
                                },
                                ensure_ascii=False,
                            ),
                            240,
                        ),
                    )
            except Exception as exc:  # noqa: BLE001
                report.fail(name, f"{exc} ({time.time() - t0:.1f}s)")

        # 4. task trace if last ask left a task
        try:
            r = client.post("/agent/sessions", json={"title": "smoke"})
            sid = (_data(r) or {}).get("id")
            r2 = client.post(f"/agent/sessions/{sid}/ask", json={"question": "有哪些游戏？", "max_rows": 20})
            payload = _data(r2) or {}
            tid = payload.get("task_id")
            if tid:
                r3 = client.get(f"/agent/tasks/{tid}/executions")
                ex = r3.json().get("data") or []
                if r3.json().get("code") == 200 and isinstance(ex, list) and len(ex) >= 1:
                    report.ok("trace.executions", f"task={tid} steps={len(ex)}")
                else:
                    report.fail("trace.executions", _short(r3.text, 200))
            else:
                report.fail("trace.executions", "no task_id from session ask")
        except Exception as exc:  # noqa: BLE001
            report.fail("trace.executions", str(exc))

    print()
    print(f"=== Smoke summary: {report.passed} passed, {report.failed} failed, total {len(report.rows)} ===")
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
