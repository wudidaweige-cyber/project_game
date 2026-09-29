# 知识库说明（模拟素材）

本目录存放**第一阶段模拟运营知识文档**，用于后续 RAG 检索与问答验证。

# 当前状态

- ✅ Markdown 原文
- ✅ 已切分并 Embedding（`text-embedding-v4`）
- ✅ 向量写入 **Milvus Lite** 本地库：`data/milvus/ops_knowledge.db`
- ✅ 原文切片写入 PostgreSQL：`ops_knowledge_doc` / `ops_knowledge_chunk`
- ⏸ 知识问答 Agent / Supervisor 尚未串联

## 重新入库

```powershell
cd backend
.\.venv\Scripts\python -m scripts.ingest_knowledge --reset
```

或 HTTP：`POST /api/v1/knowledge/ingest?reset=true`  
检索试调：`POST /api/v1/knowledge/search` `{"query":"退款条件","top_k":5}`

## 文档清单

| 文件 | 类型 | 主题 |
|------|------|------|
| `sop-account-listing.md` | SOP | 账号上架 |
| `sop-account-offline.md` | SOP | 账号下架 |
| `sop-abnormal-order.md` | SOP | 异常订单处理 |
| `rule-refund.md` | 规则 | 退款 |
| `rule-account-mgmt.md` | 规则 | 账号管理 |
| `rule-pricing.md` | 规则 | 定价与调价 |
| `rule-risk.md` | 规则 | 风控 |

## 使用约定

1. 内容为演示虚构，术语尽量与业务表字段一致（如账号状态 `available`/`rented`/`offline`/`frozen`）。
2. 不含真实账号密码、支付信息、手机号明文。
3. 后续入库时，建议 `doc_type` 映射：`sop` / `refund` / `account` / `pricing` / `risk`。
