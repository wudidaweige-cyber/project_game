# Phase A · AI 会话与任务落库（F09）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有 Supervisor / NL2SQL / Knowledge 问答写入 `ai_session` / `ai_task` / `ai_agent_execution`，支持创建会话、提问落库、按 task 回看结论与 Agent 轨迹；前端智能问答绑定会话并展示当前任务路由。

**Architecture:** 新增 `app/services/ai_trace.py` 作为唯一落库入口（创建会话、建任务、追加 execution、收尾）。`agent_api` 增加设计文档对齐的 sessions/tasks 路由；现有 `/agent/ask` 与 `/agent/ask/stream` 在执行前后挂钩落库（同步执行、持久化状态，**本阶段不做后台队列异步**）。鉴权未落地前使用固定演示用户 `DEMO_USER_ID`（可自动确保存在于 `sys_user`）。敏感字段：SQL 经 mask 写入 `sql_text_masked`；禁止写入手机号/凭证/支付明文。

**Tech Stack:** FastAPI、SQLAlchemy 2、现有 `AiSession`/`AiTask`/`AiAgentExecution` ORM、Vue AskDialog、SSE（已有）

**Spec:** `docs/02-需求规格说明书.md` F09；`docs/04-系统设计.md` §2.4 / §3 Agent 接口；`docs/05-后续工作规划.md` Phase A

## Global Constraints

- AI 默认只读；落库不得绕过 SQL Guard 或触发业务写操作。
- `result_summary` / `input_summary` / `output_summary` 最长截断（建议 4000 字符），避免大结果集整表入日志。
- 演示用户常量：`demo-operator-000000000001`（36 字符内 UUID 风格字符串；实现时用合法 UUID：`00000000-0000-4000-8000-000000000001`）。
- 本阶段 **不** 做 JWT、异常/策略 Agent、Docker、Redis。
- 仓库约定：除非用户明确要求，**不要 git commit**（计划中的 Commit 步骤改为「暂存说明 / 等待用户确认再提交」）。
- 端口与路径：后端 `:8888`，API 前缀 `/api/v1`。

## Review Focus

1. **提问失败（LLM/SQL 错误）** → task 必须为 `failed`，且仍有至少一条 execution 或 error_message 非空。
2. **写库类 reject** → task `failed`（或 `rejected` 映射为 failed），message 含安全策略，无业务写副作用。
3. **session 不存在** → `POST .../sessions/{id}/ask` 返回明确失败（404/业务码），不创建幽灵 task。
4. **摘要过长** → 超长 answer/SQL 被截断后仍可落库，接口不 500。
5. **无 DEMO 用户时首次建会话** → 自动 upsert 演示用户，不因 FK/空 user 崩溃（本库无硬 FK，但 user_id 必填）。

---

## File Map（本阶段）

| 文件 | 职责 |
|------|------|
| `backend/app/core/db.py` | 增加 `SessionLocal` / `get_db_session()` |
| `backend/app/core/config.py` | `demo_user_id` / `demo_user_name` |
| `backend/app/services/ai_trace.py` | **新建** 会话/任务/执行记录 CRUD + mask |
| `backend/app/api/v1/agent_api.py` | sessions/tasks 路由；ask 挂钩落库 |
| `backend/app/agent/supervisor.py` | stream/JSON 结果中稳定带 `task_id`；可选 hook 回调（优先在 API 层挂钩，少改 graph） |
| `frontend/src/api/agent.js` | session CRUD + task 查询；stream 带 session_id |
| `frontend/src/components/AskDialog.vue` | 打开时建会话；展示 route；可选「查看任务」 |
| `backend/tests/test_ai_trace.py` | 落库单测 |
| `backend/tests/test_agent_sessions_api.py` | API 单测（可用 TestClient + DB） |
| `readme.md` / `.env.example` | 文档与 DEMO_USER 说明 |

---

### Task 1: DB Session 工厂 + 演示用户配置

**Files:**
- Modify: `backend/app/core/db.py`
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`（若存在）
- Test: `backend/tests/test_db_session.py`

**Interfaces:**
- Produces: `get_session_factory() -> sessionmaker`；`session_scope()` context manager yielding SQLAlchemy `Session`
- Produces Settings fields: `demo_user_id: str`、`demo_username: str = "demo_operator"`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_db_session.py
from app.core.db import session_scope
from sqlalchemy import text

def test_session_scope_executes_select():
    with session_scope() as db:
        row = db.execute(text("SELECT 1 AS n")).mappings().first()
        assert row["n"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .\.venv\Scripts\python -m pytest tests\test_db_session.py -v`  
Expected: FAIL（`session_scope` 未定义）

- [ ] **Step 3: Write minimal implementation**

在 `db.py` 增加：

```python
from contextlib import contextmanager
from collections.abc import Iterator
from sqlalchemy.orm import Session

def get_session_factory() -> sessionmaker:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal

@contextmanager
def session_scope() -> Iterator[Session]:
    factory = get_session_factory()
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

在 `config.py`：

```python
demo_user_id: str = "00000000-0000-4000-8000-000000000001"
demo_username: str = "demo_operator"
demo_display_name: str = "演示运营"
```

`.env.example` 增加对应三项注释说明（Phase B 前用于会话归属）。

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python -m pytest tests\test_db_session.py -v`  
Expected: PASS

- [ ] **Step 5: Commit（仅当用户要求时）**

```text
feat(db): add session_scope and demo user settings
```

---

### Task 2: `ai_trace` 落库服务

**Files:**
- Create: `backend/app/services/ai_trace.py`
- Test: `backend/tests/test_ai_trace.py`

**Interfaces:**
- Consumes: `session_scope`、`get_settings`、`AiSession`/`AiTask`/`AiAgentExecution`、`SysUser`
- Produces:
  - `ensure_demo_user(db) -> str`  # returns user_id
  - `create_session(*, title: str = "", user_id: str | None = None) -> dict`
  - `list_sessions(*, limit: int = 20) -> list[dict]`
  - `get_session(session_id: str) -> dict | None`
  - `create_task(*, session_id: str, question: str, task_type: str = "mixed") -> dict`
  - `append_execution(*, task_id: str, agent_name: str, step_no: int, tool_name: str = "", input_summary: str = "", output_summary: str = "", sql_text: str = "", latency_ms: int = 0, status: str = "success") -> dict`
  - `finish_task(*, task_id: str, status: str, result_summary: str = "", error_message: str = "") -> dict`
  - `get_task(task_id: str) -> dict | None`
  - `list_executions(task_id: str) -> list[dict]`
  - `mask_sql(sql: str) -> str`
  - `truncate(text: str, max_len: int = 4000) -> str`

**约定：**
- `task_type`：`data_query` | `knowledge` | `mixed` | `reject`（reject 也建 task，便于审计）
- `task.status`：`pending` → `running` → `success` | `failed`
- `mask_sql`：至少把单引号字符串字面量替换为 `'***'`（简单正则即可）

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_ai_trace.py
from app.services import ai_trace

def test_mask_sql_redacts_string_literals():
    raw = "SELECT * FROM ops_order WHERE buyer_phone = '13800138000'"
    masked = ai_trace.mask_sql(raw)
    assert "13800138000" not in masked
    assert "***" in masked

def test_create_session_and_task_roundtrip():
    session = ai_trace.create_session(title="测试会话")
    assert session["id"]
    assert session["user_id"]
    task = ai_trace.create_task(session_id=session["id"], question="最近7天GMV？", task_type="data_query")
    assert task["status"] == "pending"
    ai_trace.append_execution(
        task_id=task["id"],
        agent_name="data_agent",
        step_no=1,
        tool_name="run_readonly_sql",
        sql_text="SELECT sum(gmv) FROM ops_daily_metric WHERE x='secret'",
        output_summary="row_count=1",
    )
    ai_trace.finish_task(task_id=task["id"], status="success", result_summary="GMV=100")
    got = ai_trace.get_task(task["id"])
    assert got["status"] == "success"
    assert got["result_summary"] == "GMV=100"
    exs = ai_trace.list_executions(task["id"])
    assert len(exs) == 1
    assert "secret" not in exs[0]["sql_text_masked"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python -m pytest tests\test_ai_trace.py -v`  
Expected: FAIL（模块不存在）

- [ ] **Step 3: Write minimal implementation**

实现 `ai_trace.py` 要点：
- `ensure_demo_user`：按 `demo_user_id` 查 `SysUser`，无则插入（`password_hash="!"` 占位，不可登录也无妨）
- 所有写操作在 `session_scope()` 内完成
- `create_task` 时校验 session 存在，否则 `raise ValueError("session not found")`
- 返回 dict 字段与 ORM 对齐：`id/user_id/title/status/...`

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python -m pytest tests\test_ai_trace.py -v`  
Expected: PASS

- [ ] **Step 5: Commit（仅当用户要求时）**

```text
feat(ai): add ai_trace persistence service for sessions/tasks
```

---

### Task 3: Sessions / Tasks 查询 API

**Files:**
- Modify: `backend/app/api/v1/agent_api.py`
- Test: `backend/tests/test_agent_sessions_api.py`

**Interfaces:**
- Produces HTTP（统一 `ok`/`fail`）：
  - `POST /api/v1/agent/sessions` body: `{ "title": optional }` → `{ id, user_id, title, status }`
  - `GET /api/v1/agent/sessions?limit=20` → `list`
  - `GET /api/v1/agent/sessions/{session_id}` → session or 404
  - `GET /api/v1/agent/tasks/{task_id}` → task 详情（含 question/status/result_summary/error_message/task_type）
  - `GET /api/v1/agent/tasks/{task_id}/executions` → executions 列表

- [ ] **Step 1: Write the failing API tests**

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_create_and_get_session():
    r = client.post("/api/v1/agent/sessions", json={"title": "单元测试会话"})
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 200
    sid = body["data"]["id"]
    r2 = client.get(f"/api/v1/agent/sessions/{sid}")
    assert r2.json()["data"]["id"] == sid
```

（`get_task` 用例可在 Task 4 补全；本 Task 至少覆盖 create/list/get session。）

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python -m pytest tests\test_agent_sessions_api.py::test_create_and_get_session -v`  
Expected: FAIL 404

- [ ] **Step 3: Implement routes**

在 `agent_api.py` 增加 Pydantic 模型与上述 5 个端点，内部只调 `ai_trace.*`。  
`session not found` → `fail(404, ...)`。

- [ ] **Step 4: Run test to verify it passes**

Expected: PASS

- [ ] **Step 5: Commit（仅当用户要求时）**

```text
feat(api): add agent session and task query endpoints
```

---

### Task 4: 会话内提问（同步 JSON）落库

**Files:**
- Modify: `backend/app/api/v1/agent_api.py`
- Modify: `backend/tests/test_agent_sessions_api.py`

**Interfaces:**
- Produces: `POST /api/v1/agent/sessions/{session_id}/ask`  
  body: `{ "question", "max_rows?", "top_k?" }`  
  行为：
  1. `create_task(..., task_type="mixed")` → status pending  
  2. `finish_task` 前先把 status 置 `running`（可在 create 后立刻 `finish_task` 不用；用 `append` 前 update：在 `ai_trace` 增加 `mark_task_running(task_id)` 或 `finish_task` 前专用 `update_task_status`）  
  3. 调用 `run_supervisor(...)`  
  4. 按 `route` 写入 1～N 条 `append_execution`（supervisor / data_agent / knowledge_agent / reject）  
  5. `finish_task(success|failed)`  
  6. 返回与现 `/ask` 相同结构，**额外**带 `session_id`

**Execution 写入规则（最小可用）：**

| agent_name | 何时写 | sql_text | output_summary |
|------------|--------|----------|----------------|
| supervisor | 总是 | 空 | `route_decision=...; reason=...` |
| data_agent | route 含 data_agent | executed_sql | `row_count=...` 或 error |
| knowledge_agent | route 含 knowledge_agent | 空 | `hit_count=...; no_hit=...` |
| reject | route 含 reject | 空 | error 文本 |

同时：保留原 `POST /agent/ask` —— 内部自动 `create_session(title=question[:40])` + 同上落库，避免旧客户端裸奔无痕。

- [ ] **Step 1: Write failing test with mocked supervisor**

```python
def test_session_ask_persists_task(monkeypatch):
    from app.api.v1 import agent_api

    monkeypatch.setattr(
        agent_api,
        "run_supervisor",
        lambda q, max_rows=100, top_k=5: {
            "ok": True,
            "task_id": "ignored-will-replace",
            "question": q,
            "answer": "GMV=1",
            "route": ["supervisor", "data_agent"],
            "route_decision": "data",
            "route_reason": "test",
            "refs": [{"type": "sql", "summary": "SELECT 1"}],
            "data": {"ok": True, "executed_sql": "SELECT 1", "sql": "SELECT 1", "row_count": 1},
            "knowledge": None,
            "error": "",
        },
    )
    sid = client.post("/api/v1/agent/sessions", json={"title": "ask"}).json()["data"]["id"]
    r = client.post(f"/api/v1/agent/sessions/{sid}/ask", json={"question": "最近7天GMV?"})
    assert r.json()["code"] == 200
    tid = r.json()["data"]["task_id"]
    task = client.get(f"/api/v1/agent/tasks/{tid}").json()["data"]
    assert task["status"] == "success"
    assert "GMV" in task["result_summary"]
    exs = client.get(f"/api/v1/agent/tasks/{tid}/executions").json()["data"]
    assert any(e["agent_name"] == "supervisor" for e in exs)
    assert any(e["agent_name"] == "data_agent" for e in exs)
```

注意：落库使用的 `task_id` 应来自 `ai_trace.create_task`，响应里返回该 id（可覆盖 supervisor 内部 uuid，或以 trace id 为准）。**以 `ai_trace` 的 task.id 为对外唯一 task_id。**

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement `ask` + 抽取 `_persist_supervisor_result(session_id, question, result) -> dict`**

实现时：
- 先 `create_task` 得到 `task_id`
- 再跑 `run_supervisor`
- 再写 executions + finish
- 响应 `task_id` = 落库 id

失败路径测试（可同一文件）：

```python
def test_session_ask_failed_still_persists(monkeypatch):
    monkeypatch.setattr(
        agent_api,
        "run_supervisor",
        lambda q, max_rows=100, top_k=5: {
            "ok": False,
            "task_id": "x",
            "question": q,
            "answer": "",
            "route": ["supervisor", "reject"],
            "route_decision": "reject",
            "route_reason": "写库",
            "refs": [],
            "data": None,
            "knowledge": None,
            "error": "安全策略拒绝：不允许写库",
        },
    )
    sid = client.post("/api/v1/agent/sessions", json={}).json()["data"]["id"]
    r = client.post(f"/api/v1/agent/sessions/{sid}/ask", json={"question": "把订单改成0"})
    assert r.json()["code"] == 501
    tid = r.json()["data"]["task_id"]
    task = client.get(f"/api/v1/agent/tasks/{tid}").json()["data"]
    assert task["status"] == "failed"
    assert "拒绝" in task["error_message"] or "拒绝" in (task["error_message"] + task["result_summary"])
```

（`fail()` 需把 `task_id` 放进 `data`；若当前 `fail` 已支持 data 参数则直接传。）

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit（仅当用户要求时）**

```text
feat(api): persist supervisor ask results into ai_task
```

---

### Task 5: SSE 流式提问落库

**Files:**
- Modify: `backend/app/api/v1/agent_api.py`
- Modify: `backend/app/agent/sse.py`（如需包装 generator）
- Test: `backend/tests/test_agent_stream_persist.py`

**Interfaces:**
- Produces: `POST /api/v1/agent/sessions/{session_id}/ask/stream`  
  与现 stream 事件兼容，**首个 meta 必须含** `session_id` + `task_id`（落库 id）。
- 行为：
  1. 建 task=`running`
  2. 迭代 `run_supervisor_stream`；在 `phase=routed` 时写 supervisor execution；在 `done`/`error` 时写 data/knowledge execution（若有）并 `finish_task`
  3. 原 `/agent/ask/stream` 同样自动建匿名会话并落库

- [ ] **Step 1: Write failing test**

用 `TestClient` + `iter_lines` 或直接测包装函数 `iter_supervisor_stream_with_trace(session_id, question)`（推荐测纯函数，免 LLM）：

```python
def test_stream_wrapper_persists_on_done(monkeypatch):
    from app.api.v1.agent_api import iter_traced_supervisor_stream
    from app.services import ai_trace

    def fake_stream(question, max_rows=100, top_k=5):
        yield {"event": "meta", "phase": "start", "question": question}
        yield {"event": "meta", "phase": "routed", "route_decision": "knowledge", "route_reason": "t", "route": ["supervisor", "knowledge_agent"]}
        yield {"event": "token", "text": "可全额退款"}
        yield {"event": "done", "answer": "可全额退款", "route": ["supervisor", "knowledge_agent"], "route_decision": "knowledge", "refs": [], "sql": "", "row_count": 0, "citations": [], "no_hit": False}

    monkeypatch.setattr("app.api.v1.agent_api.run_supervisor_stream", fake_stream)
    session = ai_trace.create_session(title="stream")
    events = list(iter_traced_supervisor_stream(session["id"], "什么情况全额退款？"))
    assert any(e.get("event") == "done" for e in events)
    task_id = next(e["task_id"] for e in events if e.get("task_id"))
    task = ai_trace.get_task(task_id)
    assert task["status"] == "success"
    assert "退款" in task["result_summary"] or task["result_summary"]
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement `iter_traced_supervisor_stream` + 挂到路由**

伪代码：

```python
def iter_traced_supervisor_stream(session_id: str, question: str, max_rows=100, top_k=5):
    task = create_task(session_id=session_id, question=question, task_type="mixed")
    mark_running(task["id"])
    yield {"event": "meta", "phase": "trace", "session_id": session_id, "task_id": task["id"]}
    final = None
    try:
        for ev in run_supervisor_stream(question, max_rows=max_rows, top_k=top_k):
            ev = {**ev, "session_id": session_id, "task_id": task["id"]}
            if ev.get("event") == "meta" and ev.get("phase") == "routed":
                append_execution(... agent_name="supervisor" ...)
            if ev.get("event") == "done":
                final = ev
            if ev.get("event") == "error":
                append_execution(... status="failed" ...)
                finish_task(task_id=task["id"], status="failed", error_message=ev.get("error") or "")
            yield ev
        if final:
            # append data/knowledge executions from final fields
            finish_task(task_id=task["id"], status="success", result_summary=truncate(final.get("answer") or ""))
    except Exception as exc:
        finish_task(task_id=task["id"], status="failed", error_message=str(exc))
        yield {"event": "error", "task_id": task["id"], "error": str(exc)}
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit（仅当用户要求时）**

```text
feat(api): persist SSE supervisor streams into ai_task
```

---

### Task 6: 前端绑定会话 + 展示 task 轨迹入口

**Files:**
- Modify: `frontend/src/api/agent.js`
- Modify: `frontend/src/components/AskDialog.vue`

**Interfaces:**
- Produces:
  - `createSession(title)` / `fetchTask(taskId)` / `fetchExecutions(taskId)`
  - `askSupervisor(question, opts, onEvent)` 改为打 `POST /api/v1/agent/sessions/{sessionId}/ask/stream`
- AskDialog：`open` 时若无 `sessionId` 则创建会话；消息上展示 `task_id` 与「查看步骤」拉取 executions

- [ ] **Step 1: 手动验收清单（前端无单测框架时用此步代替红绿）**

1. `npm run dev` + 后端已启动  
2. 打开对话框 → Network 可见 `POST /agent/sessions`  
3. 发「什么情况下可以全额退款？」→ 走 `.../sessions/{id}/ask/stream`  
4. 流式出字；结束后用返回 `task_id` 调 `GET /tasks/{id}/executions` 有 supervisor/knowledge_agent  

- [ ] **Step 2: 实现 `agent.js`**

```javascript
export function createSession(title = '') {
  return postJson('/api/v1/agent/sessions', { title })
}

export function fetchTask(taskId) {
  return postJson // 改为 getJson
}

export function askSupervisor(question, { maxRows = 100, topK = 5, sessionId } = {}, onEvent) {
  if (!sessionId) throw new Error('sessionId required')
  return postSse(
    `/api/v1/agent/sessions/${sessionId}/ask/stream`,
    { question, max_rows: maxRows, top_k: topK },
    onEvent,
  )
}
```

增加 `getJson(path)` helper。

- [ ] **Step 3: 改 AskDialog**

- `sessionId` ref；`open` watch 里 `createSession('运营问答')`  
- onEvent 捕获 `task_id`  
- 气泡下展示 `路由：...`（已有）+ `任务：xxx`  
- 可选：点击加载 executions 列表（agent_name / tool_name / status）

- [ ] **Step 4: `npm run build` 通过**

- [ ] **Step 5: Commit（仅当用户要求时）**

```text
feat(frontend): bind AskDialog to agent sessions and task trace
```

---

### Task 7: 文档与冒烟

**Files:**
- Modify: `readme.md`
- Modify: `docs/05-后续工作规划.md`（Phase A 标为进行中/完成时再改）
- Optional: `开发日志-2026-09-28.md`（用户要求再写）

- [ ] **Step 1: 更新 readme 当前状态**

增加勾选：

```text
- [x] AI 会话/任务落库：sessions + tasks + executions；提问/流式可回看
```

补充接口示例：

```text
POST /api/v1/agent/sessions
POST /api/v1/agent/sessions/{id}/ask
POST /api/v1/agent/sessions/{id}/ask/stream
GET  /api/v1/agent/tasks/{task_id}
GET  /api/v1/agent/tasks/{task_id}/executions
```

- [ ] **Step 2: 本地冒烟命令**

```powershell
cd backend
.\.venv\Scripts\python -m pytest tests\test_db_session.py tests\test_ai_trace.py tests\test_agent_sessions_api.py tests\test_agent_stream_persist.py -q
```

- [ ] **Step 3: Self-check Review Focus**

对照本计划 Review Focus 五条，确认测试均覆盖。

- [ ] **Step 4: Commit（仅当用户要求时）**

```text
docs: mark Phase A session/task persistence in readme
```

---

## Spec Coverage Checklist

| 需求点 | 任务 |
|--------|------|
| F09 保存会话 | Task 2–3 |
| F09 任务状态与结论 | Task 2、4、5 |
| F09 Agent/工具调用轨迹 | Task 4–5 executions |
| F09 可按任务查询 | Task 3 GET |
| F09 敏感字段不入明文 | Task 2 `mask_sql` + truncate |
| 设计文档 sessions/ask/tasks API | Task 3–5 |
| 前端可回看（最小） | Task 6 |
| 写操作拒绝可审计 | Task 4 failed 用例 |

**明确不做（防范围蔓延）：** 异步 worker、WebSocket、JWT、会话删除/归档 UI、跨用户隔离（等 Phase B）。

---

## 实现顺序小结

```text
Task1 DB session + demo user config
  → Task2 ai_trace
  → Task3 sessions/tasks GET/POST
  → Task4 JSON ask 落库
  → Task5 SSE ask 落库
  → Task6 前端绑定
  → Task7 文档冒烟
```
