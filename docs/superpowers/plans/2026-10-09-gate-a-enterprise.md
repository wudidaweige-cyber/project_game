# Gate A 企业级深化 · 实施拆解计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按 Task 逐个实现。步骤用 checkbox（`- [ ]`）跟踪。

**Goal:** 完成 `docs/08` 定义的 **Gate A**，使项目可演示「告警/问答 → 结构化建议 → 工单人审 → 执行回写 → 效果回评」，并具备口径、租户、RBAC、评测与可交付基线。

**Architecture:** 在现有 FastAPI + LangGraph + PG + RAG 上增量：工单域 / 口径域 / 告警域 / 权限租户横切；Agent 只读，写业务只经工单执行器；前端升级为 Vue Router 多页面。

**Tech Stack:** Python · FastAPI · SQLAlchemy · LangGraph · PostgreSQL · Redis · Vue3 ·（Gate A 内迁移）TypeScript + Vue Router + Pinia · Docker Compose · pytest

**Spec:** [docs/08-项目深度强化业务需求与方向.md](../../08-项目深度强化业务需求与方向.md)

## Global Constraints

- Agent **永不**直接 `UPDATE/DELETE` 业务表；变更只经工单状态机 + 执行器。
- 指标展示 / Agent 用数优先走口径服务或语义视图（F22）。
- 查询强制 `tenant_id`（超管切换除外并记审计）（F24）。
- 密钥仅环境变量；演示数据声明为模拟。
- 小步交付：每个 Task 有测试或可演示验收；不并行开三个大选修。
- 主键风格与现库一致（UUID varchar）；审计字段沿用 `AuditMixin` 约定。

## Review Focus

- 状态机非法流转是否被硬拒绝并写审计。
- 越权是否前后端双检（403）。
- Demo 脚本是否能一条命令跑通金路径。
- Gate A 勾选是否与可运行代码一致（禁止只改文档）。

## 文件落点总览（按域）

| 域 | 新建/改造 |
|----|-----------|
| 工单 | `models/ticket.py` · `services/ticket.py` · `api/v1/ticket_api.py` · `frontend` `/tickets` |
| 回评 | `models` impact · `services/ticket_impact.py` · API impact |
| 口径 | `models/metric_def.py` · `services/metrics_catalog.py` · 视图 SQL · ingest/reconcile |
| 可观测 | 扩展 `ai_agent_execution` · `api/v1/workbench_api.py` · `/workbench/tasks` |
| 租户/RBAC | `tenant_id` 迁移 · JWT claims · `require_permissions` · seed 双租户 |
| 告警 | `models/alert.py` · scheduler · `api/v1/alert_api.py` · `/alerts` |
| 知识运营 | doc 字段 version/effective · RAG filter · `evals/rag_cases.jsonl` |
| NL2SQL | LIMIT/超时/表白名单 · `evals/nl2sql_cases.jsonl` |
| 前端 | Router + TS 渐进 · 6+ 业务页 |
| NFR | Compose 文档 · `scripts/demo_enterprise_flow.py` · 审计中间件 |

---

## 依赖关系（简图）

```text
GA-00 军规/文档锚定
  ├─► Wave1: GA-10 工单状态机 → GA-11 Action契约 → GA-12 工单前端
  │         GA-13 口径中心 → GA-14 看板接口径 → GA-15 导入对账
  │         GA-16 execution扩展 → GA-17 工作台API/页
  ├─► Wave2: GA-20 效果回评 → GA-21 告警扫描
  │         GA-22 tenant 改造 → GA-23 RBAC 四角色
  │         GA-24 知识版本+RAG评测 → GA-25 NL2SQL评测加固
  │         GA-26 前端路由产品化 → GA-27 Demo脚本+NFR
  └─► Gate A 出口验收 GA-99
```

**推荐开工顺序：** GA-00 → GA-10 → GA-11 → GA-13（可与 GA-10 并行）→ GA-12 → … 严格按 Wave，不要先做 F34 全量 TS。

---

# Wave 0 — 锚定（0.5 天）

## Task GA-00：军规与文档挂钩

**目标：** 编码前约束写死，避免实现跑偏。

**步骤：**

- [ ] 更新 `CLAUDE.md`：口径真源、工单写路径、tenant 强制、Agent 禁止直写业务表。
- [ ] `readme.md` 增加「企业级 Gate A（进行中）」章节与本计划链接。
- [ ] `docs/05` 增加指向 `docs/08` + 本计划的「下一阶段」。

**验收：** 三处文档可互相跳转；无代码行为变更。

**依赖：** 无  
**预估：** 0.5h

---

# Wave 1 — 闭环骨架（约 2～3 周）

## Task GA-10：工单领域模型 + 状态机服务（F20 后端核心）

**目标：** `ops_ticket` / `ops_ticket_event` + 合法/非法流转单测。

**步骤：**

- [ ] 新增 ORM：`OpsTicket`、`OpsTicketEvent`（字段对齐 docs/08 §4.1）。
- [ ] `scripts/init_db` / 迁移策略：与现网一致（create_all 或 alembic，本仓优先沿用 init_db）。
- [ ] `services/ticket_fsm.py`：`draft→pending_review→approved|rejected→executing→done|failed`，`cancelled` 自 draft/pending。
- [ ] 写失败测试：非法边抛错；合法边写 event。
- [ ] 实现 FSM 使测试通过。
- [ ] 审计：每次流转写 `sys_audit_log`（若现有 audit 未接线，先落 event 表 + TODO audit helper）。

**验收：** `pytest tests/test_ticket_fsm.py` 覆盖全部合法边 + ≥5 非法边。

**依赖：** GA-00  
**预估：** 1～2 天  
**修改文件（预期）：** `backend/app/models/ticket.py`、`services/ticket*.py`、`tests/test_ticket_fsm.py`、`models/__init__.py`

---

## Task GA-11：工单 HTTP API + 从 AI Task 生成

**目标：** REST 完整流转；策略结果可生成 draft。

**步骤：**

- [ ] `api/v1/ticket_api.py`：create/list/get/submit/approve/reject/execute/cancel/events。
- [ ] `POST /tickets` 支持 `source_ai_task_id` 拉取策略摘要填 `ai_summary`/`payload_json`。
- [ ] reject 无 `reason` → 400。
- [ ] 权限占位：暂用 `admin`≈审批、`operator`≈创建/提交（GA-23 再换成四角色）。
- [ ] API 测试：越权 403、状态流转 200。

**验收：** 用 Token 手工走完 create→submit→approve→execute→done；pytest ≥8 条。

**依赖：** GA-10  
**预估：** 1～2 天

---

## Task GA-12：策略 Agent 输出 Action JSON 契约

**目标：** 策略/异常路径尽量产出可解析 `actions[]`。

**步骤：**

- [ ] 定义 schema（Pydantic）：`ActionItem`（对齐 docs/08 JSON）。
- [ ] 改 `agent/strategy.py`（及必要时 anomaly）Prompt + 解析；失败则 `actions=[]` 不崩。
- [ ] Supervisor/API 响应增加 `actions` 字段（向后兼容）。
- [ ] 单测：样例模型输出可解析；畸形输出降级。

**验收：** 策略问答响应含 `actions`；可被 GA-11「一键建单」使用。

**依赖：** GA-10（可与 GA-11 并行后半）  
**预估：** 1 天

---

## Task GA-13：口径中心表 + 语义视图（F22 数据真源）

**目标：** `ops_metric_def` + 视图 `vw_metric_daily_tenant`（无租户前可先 `vw_metric_daily`）。

**步骤：**

- [ ] ORM + seed 口径：gmv/order_count/rent_rate/refund_rate。
- [ ] SQL 视图脚本：`backend/scripts/sql/vw_metric_daily.sql`（或 init 时执行）。
- [ ] `services/metrics_catalog.py`：按 code 取定义；看板查询入口改调用点准备。
- [ ] 测试：定义存在；视图可 SELECT。

**验收：** 文档说明「口径真源」；视图查询与旧 overview 数量级一致（允许小数差）。

**依赖：** GA-00  
**预估：** 1～2 天  
**说明：** `tenant_id` 可先占位常量 `default`，GA-22 再强制。

---

## Task GA-14：看板改走口径服务

**目标：** `dashboard` overview/trends/rank 走口径层，不再散落裸 SQL（或薄封装）。

**步骤：**

- [ ] 重构 `services/dashboard.py` 调用口径服务。
- [ ] 回归 `tests/test_dashboard.py`。
- [ ] readme/手册补一句：指标来自口径定义。

**验收：** 驾驶舱数字与改造前一致（同日期窗口）。

**依赖：** GA-13  
**预估：** 0.5～1 天

---

## Task GA-15：CSV/JSON 订单导入 + 日对账（F22）

**目标：** 脏数据可导入、可对账失败。

**步骤：**

- [ ] `POST /api/v1/ingest/orders`（admin）；解析 CSV/JSON。
- [ ] `ops_reconcile_run` 表 + 任务：订单聚合 vs daily_metric，超阈值记失败。
- [ ] 样例：`data/fixtures/dirty_orders.csv`。
- [ ] 测试：正常导入；脏数据触发 reconcile fail。

**验收：** 样例包可复现对账失败记录。

**依赖：** GA-13  
**预估：** 1～2 天

---

## Task GA-16：扩展 ai_agent_execution（F23 数据）

**目标：** Token/费用/错误码字段可落库。

**步骤：**

- [ ] 模型加字段：`token_input`/`token_output`/`cost_estimate`/`error_code`/`tool_name`（已有则补齐）。
- [ ] `ai_trace` 写入点挂钩（能拿则拿，拿不到填 0/空）。
- [ ] 测试：创建任务后 execution 有新字段。

**验收：** DB 行可见扩展列。

**依赖：** 无强依赖，可并行  
**预估：** 0.5～1 天

---

## Task GA-17：Agent 工作台 API + 最小前端页（F23）

**目标：** 任务列表/详情时间线可回放。

**步骤：**

- [ ] `GET /api/v1/workbench/tasks`、`GET .../tasks/{id}`（含 executions）。
- [ ] 前端：先做驾驶舱内「工作台」对话框或路由页 v0（GA-26 再正式路由）。
- [ ] 验收脚本：跑一次 anomaly_knowledge，工作台能看到 Guard/工具步骤。

**验收：** 3 分钟内能定位一次 SQL_GUARD 或成功路径。

**依赖：** GA-16  
**预估：** 1～2 天

---

## Wave 1 出口检查

- [ ] Demo：策略问答 → 生成 draft 工单 → 审批 → execute（可 mock）→ done。
- [ ] 口径表有数据；看板仍可用。
- [ ] 工作台能打开一条任务详情。
- [ ] 回写 `docs/04` 新表/接口草案。

---

# Wave 2 — Gate A 齐套（约 2～3 周）

## Task GA-20：效果回评 F21

**目标：** `ops_ticket_impact` + 前后窗口对比 + 人工打标。

**步骤：**

- [ ] 表 + `GET/POST impact` / `label` / `recompute`。
- [ ] 计算走口径服务；支持 Demo「快进」写快照。
- [ ] 前端工单详情展示效果卡片。
- [ ] 测试：done 工单可出 delta。

**依赖：** GA-11、GA-14  
**预估：** 1～2 天

---

## Task GA-21：异常告警扫描 F26

**目标：** 规则表 + 定时扫描 + 转问答。

**步骤：**

- [ ] `ops_alert_rule` / `ops_alert_event`。
- [ ] 进程内调度（APScheduler 或 lifespan 线程）；冷却时间。
- [ ] `POST /alerts/{id}/ask` 带上下文建 session。
- [ ] seed：一条出租率阈值规则；测试注入暴跌指标 → open。
- [ ] 前端告警列表 v0。

**依赖：** GA-14；转问答依赖现有 agent sessions  
**预估：** 2 天

---

## Task GA-22：逻辑多租户 F24

**目标：** 业务/知识/AI/工单/告警表 `tenant_id` + 强制过滤。

**步骤：**

- [ ] 迁移加列（默认 `t_demo`）；seed 第二租户 `t_other`。
- [ ] JWT 增加 `tenant_id`；deps 注入。
- [ ] MCP / dashboard / ticket / knowledge 查询强制 tid。
- [ ] 反例测试：跨租户读 403/空；SQL 无租户策略写死并测。

**依赖：** Wave1 主体完成（改表面广）  
**预估：** 2～3 天  
**风险：** 最大；单独开 PR，全量回归。

---

## Task GA-23：RBAC 四角色 F25

**目标：** `tenant_admin` / `ops_lead` / `operator` / `analyst` + 权限点。

**步骤：**

- [ ] 角色与权限表或 JWT permissions 列表。
- [ ] `require_permissions("ticket:approve")` 等。
- [ ] 映射旧 `admin`→`tenant_admin`；seed 四账号。
- [ ] 越权矩阵 pytest ≥12。
- [ ] 前端按权限藏按钮（指令或 computed）。
- [ ] 产出 `docs/rbac-matrix.md`。

**依赖：** GA-22（claims 一起做更顺）  
**预估：** 2 天

---

## Task GA-24：知识版本/生效期 + RAG 评测 F27

**目标：** published+生效期过滤；≥30 题评测报告。

**步骤：**

- [ ] doc 字段：version/effective_from/effective_to/status 增强。
- [ ] retriever 过滤。
- [ ] `backend/evals/rag_cases.jsonl` ≥30；runner → `rag_report.md`。
- [ ] （可选）无命中创建 knowledge_gap 工单。

**依赖：** 现有 RAG；工单可选依赖 GA-11  
**预估：** 1～2 天

---

## Task GA-25：NL2SQL 加固 + 金标 F28

**目标：** LIMIT/超时/表白名单；≥30 题报告。

**步骤：**

- [ ] sql_guard：强制 LIMIT、超时、视图白名单。
- [ ] Prompt 引导优先 `vw_metric_*`。
- [ ] `evals/nl2sql_cases.jsonl` ≥30；报告。
- [ ] 并发/限流：每用户简单令牌桶（可 Redis 或内存）。

**依赖：** GA-13 视图；GA-22 租户谓词  
**预估：** 2 天

---

## Task GA-26：前端产品化 F34（Gate A 最小集）

**目标：** Router + 至少 6 个业务页；TS 可渐进（先 JS Router 也可，但 Gate A 要求 TS——按模块迁移）。

**页面最低集：**

```text
/login
/dashboard
/ask
/tickets
/alerts
/knowledge
/workbench/tasks
```

**步骤：**

- [ ] 引入 Vue Router（+ Pinia）；拆 Dashboard 壳。
- [ ] 迁移 ChatWorkspace → `/ask`；知识管理 → `/knowledge`。
- [ ] 工单/告警/工作台正式页（替换对话框 v0）。
- [ ] `v-permission` 或等价；`npm run build` 通过。

**依赖：** GA-11/17/21 UI 已有 API  
**预估：** 3～4 天

---

## Task GA-27：NFR 交付与企业 Demo 脚本

**目标：** 一键演示金路径 + Compose/测试门禁说明。

**步骤：**

- [ ] `scripts/demo_enterprise_flow.py`：告警→问答→工单→审批→执行→回评。
- [ ] 更新 `docker/README.md`：依赖 + 应用启动顺序；SLO 基线写入 readme（实测或标注未测）。
- [ ] 统一审计中间件或关键路径审计补齐。
- [ ] pytest 全绿；eval smoke 5 题脚本。

**依赖：** Wave2 功能主体  
**预估：** 1～2 天

---

## Task GA-99：Gate A 出口验收

**检查清单（对照 docs/08 §0.2）：**

- [ ] F20～F28、F34、NFR 均有可运行证据（非仅文档）
- [ ] `docs/08` Gate A 勾选更新
- [ ] `docs/04`/`02`/`07`/`readme` 已回写
- [ ] 简历条目数字可替换为实测
- [ ] Demo 脚本无人值守跑通（或逐步脚本 + 录像说明）

**预估：** 0.5～1 天

---

# 任务粒度总表（便于排期）

| ID | 名称 | Wave | 依赖 | 预估 |
|----|------|------|------|------|
| GA-00 | 军规文档 | 0 | — | 0.5h |
| GA-10 | 工单 FSM | 1 | 00 | 1～2d |
| GA-11 | 工单 API | 1 | 10 | 1～2d |
| GA-12 | Action JSON | 1 | 10 | 1d |
| GA-13 | 口径中心 | 1 | 00 | 1～2d |
| GA-14 | 看板接口径 | 1 | 13 | 0.5～1d |
| GA-15 | 导入对账 | 1 | 13 | 1～2d |
| GA-16 | execution 扩展 | 1 | — | 0.5～1d |
| GA-17 | 工作台 | 1 | 16 | 1～2d |
| GA-20 | 效果回评 | 2 | 11,14 | 1～2d |
| GA-21 | 告警 | 2 | 14 | 2d |
| GA-22 | 多租户 | 2 | W1 | 2～3d |
| GA-23 | RBAC | 2 | 22 | 2d |
| GA-24 | 知识评测 | 2 | RAG | 1～2d |
| GA-25 | NL2SQL 评测 | 2 | 13,22 | 2d |
| GA-26 | 前端产品化 | 2 | API 齐 | 3～4d |
| GA-27 | Demo+NFR | 2 | W2 | 1～2d |
| GA-99 | 出口验收 | 2 | all | 0.5～1d |

**合计粗估：** 约 4～6 周（单人全职）；双人可 Wave1 工单∥口径并行。

---

# 执行约定

1. **一次只做一个 Task ID**；完成再勾选本文件与 `docs/08` Gate A 对应项。  
2. 每个 Task：**测试或 Demo 命令写进 PR/回复**；禁止「只建表不接线」。  
3. GA-22 单独分支，全量回归。  
4. 前端 TS：允许「新页 TS、旧页 JS」渐进，但 GA-26 结束时 `npm run build` 必须绿。  
5. 实现时优先读：`docs/08` 对应 F 节 + 本 Task「步骤/验收」。

---

# 建议的第一刀（你确认后立即开工）

**GA-00 → GA-10**（工单状态机 + 单测），不碰租户与前端大改。

回复「从 GA-00/GA-10 开始」即按该顺序改代码。
