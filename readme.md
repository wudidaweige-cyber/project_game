# 游戏平台账号租赁智能运营分析系统

面向游戏账号租赁平台的智能运营分析系统：运营数据看板、自然语言数据分析（NL2SQL）、异常分析、运营知识库（RAG）与 Multi-Agent（LangGraph + MCP）辅助决策。

第一阶段目标：**可运行、可演示、可扩展**。策略分析仅输出建议，不直接改写业务数据。  
前期原则：**本机跑通功能，不追求 Docker 部署。**

## 文档

| 文档 | 说明 |
|---|---|
| [docs/01-游戏平台账号租赁智能运营分析系统_项目开发需求前置文档_V1.0.md](docs/01-游戏平台账号租赁智能运营分析系统_项目开发需求前置文档_V1.0.md) | 项目前置需求（业务真源） |
| [docs/02-需求规格说明书.md](docs/02-需求规格说明书.md) | 软件需求规格说明书（开发与验收基准） |
| [docs/03-前期准备清单.md](docs/03-前期准备清单.md) | 开工前环境、密钥、口径、素材与 Demo 检查清单 |
| [docs/04-系统设计.md](docs/04-系统设计.md) | 系统架构、数据库设计、接口设计 |
| [docs/05-后续工作规划.md](docs/05-后续工作规划.md) | 进度盘点与分阶段后续规划 |
| [CLAUDE.md](CLAUDE.md) | AI Coding Agent 协作规范 |
| [开发日志-2026-09-22.md](开发日志-2026-09-22.md) | 2026-09-22 任务与完成情况 |
| [开发日志-2026-09-23.md](开发日志-2026-09-23.md) | 2026-09-23 任务与完成情况 |

## 目录结构

```text
game/
├── .env / .env.example
├── backend/              # FastAPI（已落地骨架）
│   ├── app/
│   └── tests/
├── frontend/             # Vue + Vite（已落地骨架）
├── docs/
├── CLAUDE.md
└── readme.md
```

## 本地运行

### 1. 环境变量

根目录配置 `.env`（可从 `.env.example` 复制）。至少保证：

- `DATABASE_URL` 可连，且库 `game_ops` 已存在
- `APP_PORT=8888`

### 2. 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8888 --reload
```

验证：

- 浏览器打开 http://127.0.0.1:8888/docs
- 或访问 http://127.0.0.1:8888/api/v1/health  
  期望：`code=200`，`data.status=ok`，`data.database.ok=true`

测试：

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q
```

端到端冒烟（需后端已在 `:8888` 运行，演示账号 `operator` / `Operator@123`）：

```powershell
cd backend
.\.venv\Scripts\python -m scripts.smoke_e2e
```

### 3. 前端

```powershell
cd frontend
npm install
# 若官方源不稳定，可用：
# npm install --registry=https://registry.npmmirror.com
npm run dev
```

浏览器打开 http://127.0.0.1:5173 ，页面应显示后端健康状态（经 Vite 代理 `/api` → `:8888`）。

## 当前状态

- [x] 需求 / SRS / 准备清单 / 系统设计
- [x] 后端骨架：配置加载、统一响应、健康检查、PostgreSQL ping
- [x] 前端骨架：Vue 壳 + 健康检查联调页（需本机 `npm install`）
- [x] 业务表结构（`sys_*` / `ops_*` / `ai_*`）+ `scripts.init_db`
- [x] 模拟数据：`scripts.seed_demo`（6 游戏 / 60 天）
- [x] 运营看板 API：`/api/v1/dashboard/overview|trends|game-rank|games/{id}`
- [x] 运营看板前端：ECharts 驾驶舱（指标卡 / 趋势 / 排行 / 游戏详情）
- [x] MCP 只读工具：`list_games` / `query_gmv` / `query_rent_rate` / `query_orders_summary` / `query_game_metric_rank` / `run_readonly_sql`
- [x] NL2SQL Agent：`POST /api/v1/agent/nl2sql`（生成 → 结构自检/安全校验 → 失败重试 1 次 → MCP 执行 → 结论）
- [x] 模拟知识库原文：`data/knowledge/*.md`
- [x] RAG 向量化入库：切分 + Embedding + Milvus Lite + PG 切片表
- [x] RAG Hybrid：向量 + BM25 + RRF；可选 Rerank（`RAG_RERANK_ENABLED`）
- [x] 知识问答 Agent：`POST /api/v1/agent/knowledge`（检索 →  grounded 作答 / 无命中不编造）
- [x] Supervisor：`POST /api/v1/agent/ask`（LangGraph 路由 data/knowledge/both/anomaly/strategy → 汇总）
- [x] AI 会话/任务落库：`sessions` + `tasks` + `executions`；提问/流式可回看
- [x] 登录鉴权：JWT；演示账号 operator/admin；看板/Agent/MCP 需登录
- [x] 异常分析 Agent：窗口对比 + 游戏下钻；路由 `anomaly` / `anomaly_knowledge`
- [x] 策略分析 Agent：指标快照 → 只读建议；路由 `strategy` / `strategy_knowledge`；禁止写库

### 登录鉴权（F01）

```text
POST /api/v1/auth/login   {"username":"operator","password":"Operator@123"}
GET  /api/v1/auth/me
POST /api/v1/auth/logout
```

演示账号：
- `operator` / `Operator@123`（运营）
- `admin` / `Admin@123`（管理员；知识入库需 admin）

前端打开先登录；`Authorization: Bearer <token>` 访问受保护接口。

### 会话与任务（F09）

```text
POST /api/v1/agent/sessions
POST /api/v1/agent/sessions/{id}/ask
POST /api/v1/agent/sessions/{id}/ask/stream
GET  /api/v1/agent/tasks/{task_id}
GET  /api/v1/agent/tasks/{task_id}/executions
```

前端「智能」模式打开对话框时自动建会话；回答可展开「查看执行步骤」。

### 异常分析

```text
POST /api/v1/agent/anomaly
{"question":"最近出租率为何异常？"}

# 或走 Supervisor（智能模式自动路由）
POST /api/v1/agent/ask
{"question":"最近出租率为何异常？按退款规则该怎么处理？"}
```

对比「近 N 天 vs 前 N 天」全站 GMV/订单/出租率/退款率，并下钻贡献游戏；可再串联知识 Agent。

### 策略分析（只建议不写库）

```text
POST /api/v1/agent/strategy
{"question":"根据最近指标给出运营策略建议","with_knowledge":false}

# 或走 Supervisor（智能模式自动路由）
POST /api/v1/agent/ask
{"question":"按定价规则给出调价建议"}
```

基于窗口指标快照生成运营建议；可选串联知识库。硬性约束：只输出建议，对话写库/改价落库会被拒绝。

### Supervisor

```text
POST /api/v1/agent/ask
{"question":"最近出租率为何异常？按退款规则该怎么处理？"}
```

返回：`answer`、`route`、`route_decision`、`refs`；前端对话框默认「智能」模式。

### 流式问答（前端默认）

```text
POST /api/v1/agent/ask/stream
POST /api/v1/agent/nl2sql/stream
POST /api/v1/agent/knowledge/stream
```

SSE 事件：`phase` / `meta` / `token` / `done` / `error`。非流式 JSON 接口仍保留便于脚本调试。

### 知识问答

```text
POST /api/v1/agent/knowledge
{"question":"什么情况下可以全额退款？","top_k":5}
```

前端对话框可切换「问数 / 问规则」。

### 模拟知识库 / RAG

目录：`data/knowledge/`  
入库：

```powershell
cd backend
.\.venv\Scripts\python -m scripts.ingest_knowledge --reset
```

- 向量：Milvus Lite（`MILVUS_URI` 留空即可）  
- 原文切片：PostgreSQL `ops_knowledge_*`  
- 检索默认 Hybrid：`向量 + BM25 → RRF`；`POST /api/v1/knowledge/search` 可传 `"mode":"vector"|"hybrid"`  
- 可选 Rerank：`.env` 设 `RAG_RERANK_ENABLED=true` 并配置 `RERANK_*`（失败自动回退）  
- 入库后会重建进程内 BM25 索引；首次检索若索引为空会惰性从 PG 加载

### NL2SQL

```text
POST /api/v1/agent/nl2sql
{"question":"最近7天GMV是多少？","max_rows":100}
```

返回：`answer`、`sql`、`rows`、`row_count`、`task_id`；失败重试时带 `sql_attempts`。  
稳定性：Schema 含 CTE/排行模板；提取优先保留 `WITH`；缺 `WITH` 自动补全；括号/FROM 自检；校验或执行失败最多再生成 1 次。

### MCP 使用

HTTP（需后端已启动）：

```text
GET  /api/v1/mcp/tools
POST /api/v1/mcp/tools/{name}/call
     body: { "arguments": { ... } }
```

stdio MCP Server（供 Cursor / Agent 接入）：

```powershell
cd backend
.\.venv\Scripts\python -m app.mcp.server
```

### 建表与灌数

```powershell
cd backend
.\.venv\Scripts\python -m scripts.init_db --drop
.\.venv\Scripts\python -m scripts.seed_demo
```

看板接口示例：

```text
GET /api/v1/dashboard/overview?start_date=2026-09-01&end_date=2026-09-22
GET /api/v1/dashboard/trends?metric=gmv&start_date=2026-09-01&end_date=2026-09-22
GET /api/v1/dashboard/game-rank?metric=gmv&start_date=2026-09-01&end_date=2026-09-22&limit=5
```

## 下一步

详见 [docs/05-后续工作规划.md](docs/05-后续工作规划.md)。

当前建议优先：**Phase D 策略分析 Agent** → 检索/SQL 质量 → LangSmith / Redis / Docker 后置。  
Phase A～C（会话落库、登录鉴权、异常分析）已完成。

## 贡献约定

开发请遵循 `CLAUDE.md`：小步 Task、安全优先、完成后给出运行与验证说明。
