from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base


class OpsKnowledgeDoc(Base, AuditMixin):
    __tablename__ = "ops_knowledge_doc"
    __table_args__ = {"comment": "知识库文档"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID")
    title: Mapped[str] = mapped_column(String(256), nullable=False, comment="标题")
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="sop/refund/account/pricing/risk")
    source_path: Mapped[str] = mapped_column(String(512), nullable=False, default="", comment="源文件路径")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", comment="draft/published")
    embed_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", comment="pending/running/success/failed"
    )


class OpsKnowledgeChunk(Base, AuditMixin):
    __tablename__ = "ops_knowledge_chunk"
    __table_args__ = {"comment": "知识切片原文"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="chunk_id，与Milvus对齐")
    doc_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="文档ID")
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="文档类型冗余")
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="切片序号")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="原文")
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="token估算")
    milvus_collection: Mapped[str] = mapped_column(String(64), nullable=False, default="ops_knowledge", comment="集合名")
