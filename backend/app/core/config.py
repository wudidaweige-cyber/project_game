from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# 仓库根目录的 .env（backend 的上一级）
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT_ENV) if _ROOT_ENV.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8888
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/game_ops"
    database_readonly_url: str | None = None

    jwt_secret: str = "please-change-me"
    jwt_expire_minutes: int = 720

    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen-plus"

    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "text-embedding-v4"
    embedding_dim: int = 1024

    # RAG hybrid / rerank
    rag_hybrid_enabled: bool = True
    rag_candidate_k: int = 20
    rag_rrf_k: int = 60
    rag_rerank_enabled: bool = False
    rag_rerank_top_n: int = 10
    rerank_base_url: str | None = None
    rerank_api_key: str | None = None
    rerank_model: str = ""

    # 本机可用本地文件（Milvus Lite）；也可填 http://127.0.0.1:19530
    milvus_uri: str = ""
    milvus_token: str = ""
    milvus_collection: str = "ops_knowledge"

    knowledge_dir: str = ""

    ai_sql_readonly: bool = True
    strategy_allow_write: bool = False
    agent_timeout_seconds: int = 120

    # Phase A：鉴权落地前会话归属演示用户（Phase B 换真实登录用户）
    demo_user_id: str = "00000000-0000-4000-8000-000000000001"
    demo_username: str = "demo_operator"
    demo_display_name: str = "演示运营"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def readonly_database_url(self) -> str:
        return self.database_readonly_url or self.database_url

    @property
    def resolved_embedding_base_url(self) -> str:
        return (self.embedding_base_url or self.llm_base_url).rstrip("/")

    @property
    def resolved_embedding_api_key(self) -> str:
        return self.embedding_api_key or self.llm_api_key

    @property
    def resolved_rerank_base_url(self) -> str:
        return (self.rerank_base_url or "").rstrip("/")

    @property
    def resolved_rerank_api_key(self) -> str:
        return self.rerank_api_key or ""

    @property
    def resolved_milvus_uri(self) -> str:
        raw = self.milvus_uri.strip()
        root = Path(__file__).resolve().parents[3]
        lite_path = root / "data" / "milvus" / "ops_knowledge.db"
        lite_path.parent.mkdir(parents=True, exist_ok=True)
        # 空值或仍指向本机默认未启动端口时，使用 Milvus Lite 本地文件
        if not raw or raw in {
            "http://127.0.0.1:19530",
            "http://localhost:19530",
        }:
            return str(lite_path)
        return raw

    @property
    def resolved_knowledge_dir(self) -> Path:
        if self.knowledge_dir.strip():
            return Path(self.knowledge_dir)
        return Path(__file__).resolve().parents[3] / "data" / "knowledge"

@lru_cache
def get_settings() -> Settings:
    return Settings()
