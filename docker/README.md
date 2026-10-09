# 基础设施 Docker Compose（档 A）

应用（FastAPI / Vue）**不进容器**。本目录只编排：

- **默认：** Milvus standalone（etcd + MinIO + Milvus），端口 `19530`
- **默认：** Redis，端口 `6379`（Agent 异步队列；Windows 也可留空 `REDIS_URL` 用进程内队列）
- **可选：** PostgreSQL `game_ops`，需加 `--profile with-pg`

后端 / 前端镜像 / Nginx 不在本档范围。

## 1. 虚拟机上启动

要求：已安装 Docker 与 Docker Compose 插件。

```bash
cd /path/to/game/docker
docker compose up -d
docker compose ps
```

等待 `game-ops-milvus` 变为 healthy（首次约 1～2 分钟）。

防火墙放行（示例）：

```bash
sudo ufw allow 19530/tcp
# 或 firewalld：
# sudo firewall-cmd --permanent --add-port=19530/tcp && sudo firewall-cmd --reload
```

查看虚拟机 IP：

```bash
hostname -I
```

## 2. Windows 本机改 `.env`

把仓库根目录 `.env` 中的地址改成虚拟机 IP（**不要**填 `127.0.0.1`，代码会把它当成 Milvus Lite 回退）：

```env
MILVUS_URI=http://192.168.x.x:19530
MILVUS_TOKEN=
MILVUS_COLLECTION=ops_knowledge
```

连通检查（PowerShell）：

```powershell
Test-NetConnection 192.168.x.x -Port 19530
```

`TcpTestSucceeded : True` 后再重启后端。

## 3. 重新入库（换 Milvus 必须做）

Lite 或旧实例里的向量不会自动迁移。

```powershell
cd backend
.\.venv\Scripts\python -m scripts.ingest_knowledge --reset
```

期望输出含 `"ok": true` 且 `milvus_uri` 为虚拟机地址。

## 4. 可选：PostgreSQL 也放进 Compose

若希望业务库也在虚拟机容器里（本机不再自装 PG）：

```bash
cd docker
docker compose --profile with-pg up -d
```

Windows `.env`：

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@192.168.x.x:5432/game_ops
DATABASE_READONLY_URL=postgresql+psycopg://postgres:postgres@192.168.x.x:5432/game_ops
```

然后本机：

```powershell
cd backend
.\.venv\Scripts\python -m scripts.init_db
.\.venv\Scripts\python -m scripts.seed_demo
.\.venv\Scripts\python -m scripts.ingest_knowledge --reset
```

注意：虚拟机 `5432` 需对 Windows 放行。若本机已有 PostgreSQL 占用演示，不要同时映射冲突端口，或继续用本机 PG、只跑默认的 Milvus 服务。

## 5. 常用命令

```bash
docker compose ps
docker compose logs -f milvus
docker compose down          # 停容器，数据卷保留
docker compose down -v       # 停并删除数据（向量/库都会没）
```

## 6. 与「已有官方 Milvus Compose」并存

若虚拟机里已经用官方 `milvus-standalone-docker-compose.yml` 在跑，且 `19530` 已通：

- **可以不切换**，Windows 继续指那个 IP 即可。
- 本仓库文件用于可复现、换机重建。不要两套同时占用 `19530`。

## 7. 不做的事（档 B）

后端 / 前端镜像、Nginx 反代、Redis 不在本 compose 中。
