# 游戏平台账号租赁智能运营分析系统 · 开发协作规范

## 1. 角色

你是本项目的 AI Coding Agent。工作方式不是一次性生成整个系统，而是根据前置需求文档、SRS 与当前 Task，逐步实现可运行、可测试、可维护的代码。

## 2. 必须遵循的文档

开发前优先阅读：

1. `docs/01-游戏平台账号租赁智能运营分析系统_项目开发需求前置文档_V1.0.md`
2. `docs/02-需求规格说明书.md`
3. `docs/04-系统设计.md`（架构 / 库表 / 接口约定）
4. `readme.md`
5. 开工前另读：`docs/03-前期准备清单.md`（环境、密钥、指标口径、模拟素材、Demo 问题）

如果代码实现与需求冲突，以客户前置需求与 SRS 为准；如果发现需求存在歧义，不要静默猜测，应明确提出。

## 3. 技术约束

未经明确要求，不要随意替换核心技术栈。

| 层级 | 选型 |
|---|---|
| Frontend | Vue、ECharts |
| Backend | Python + FastAPI |
| Agent | LangChain、LangGraph（Supervisor + Multi-Agent） |
| Model | Qwen / DeepSeek / 其他 OpenAI Compatible |
| Database | PostgreSQL；Redis（可后置） |
| RAG | Milvus、Embedding、BM25、Hybrid Search、RRF、Rerank |
| Tooling | MCP、Function Calling |
| Observability | LangSmith（可配置） |
| Deployment | 前期本机跑通；Docker / Compose **后置，不阻塞功能** |

## 4. 开发原则

### 4.1 小步实现

禁止：

```text
一次性实现整个智能运营分析系统
```

推荐（与 MVP 对齐）：

```text
SRS / 前置需求
 ↓
项目骨架（FastAPI + Vue）
 ↓
业务数据模型 + 模拟数据
 ↓
运营数据看板 API / 前端
 ↓
MCP Server（只读业务查询工具）
 ↓
RAG 知识库
 ↓
NL2SQL / 数据分析 Agent
 ↓
Supervisor 串联（数据 Agent + 知识 Agent）
 ↓
端到端演示跑通（本机进程，不依赖 Docker）
 ↓
异常分析 / 策略分析（功能稳定后）
 ↓
LangSmith / Redis / Docker 部署（工程化后置）
 ↓
测试与演示脚本
```

**前期优先级：** 功能实现与整体跑通 > 工程化部署。不要把 Docker/Nginx 当作 MVP 验收条件。

### 4.2 Task 驱动

每次实现 Task 必须明确：

- 背景
- 目标
- 输入
- 输出
- 修改文件
- 技术约束
- 验收标准
- 不应修改的范围

### 4.3 安全优先

- 不把 API Key、数据库凭证写入代码或提交到仓库。
- AI 数据分析默认只允许 SELECT；禁止 INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE 等写操作。
- 对模型生成的 SQL 做语法、表权限与危险操作检查后再执行。
- 手机号、账号凭证、支付信息等敏感字段不得直接进入模型上下文，必要时脱敏。
- 不同 Agent 仅开放完成自身任务所需的 MCP 工具。
- 第一阶段运营策略只输出建议，不得直接修改业务数据。
- 第三方接口 / 模型调用失败必须有明确错误处理与可定位日志。

### 4.4 AI Agent 原则

Agent 必须有明确职责，不为了“多 Agent”而增加 Agent。

推荐职责：

```text
Supervisor
 ├── 数据分析 Agent（NL2SQL / 指标查询）
 ├── 异常分析 Agent
 ├── 知识 Agent（RAG）
 └── 策略分析 Agent
```

MVP 最低要求：Supervisor + 数据分析 Agent + 知识 Agent 可串联。

工具调用必须可追踪；重要执行必须记录任务/会话状态。

## 5. RAG 原则

运营知识检索链路应支持：

```text
Query
 ↓
Metadata Filter（文档类型等）
 ↓
Vector Search（必要时 Hybrid / RRF）
 ↓
必要时 Rerank
 ↓
Context
 ↓
LLM
```

- 检索无结果时明确说明“无知识依据”，禁止伪造运营规则。
- 回答应尽量可追溯到来源文档/切片。
- 第一阶段可用模拟 SOP/退款/定价/风控文档验证检索质量。

## 6. 代码质量

- 使用类型注解。
- 模块职责清晰：业务 API、Agent、MCP、RAG、看板查询分离。
- 避免超长函数。
- 错误信息要可定位（含任务/会话 ID）。
- 新功能必须有基础测试或可复现验证方式。
- 不修改与当前 Task 无关的文件。

## 7. 完成 Task 后

必须说明：

1. 实现了什么。
2. 修改了哪些文件。
3. 如何运行。
4. 如何验证。
5. 已知限制。
6. 下一步建议。

不要声称未实际验证的功能已经完全可用。
