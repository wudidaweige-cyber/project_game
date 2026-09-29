from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base


class AiSession(Base, AuditMixin):
    __tablename__ = "ai_session"
    __table_args__ = {"comment": "AI会话"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID")
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="系统用户ID")
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="", comment="标题")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", comment="状态")


class AiTask(Base, AuditMixin):
    __tablename__ = "ai_task"
    __table_args__ = {"comment": "AI分析任务"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID")
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="会话ID")
    task_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="data_query/knowledge/anomaly/strategy/mixed"
    )
    question: Mapped[str] = mapped_column(Text, nullable=False, comment="用户问题")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True, comment="状态")
    result_summary: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="结果摘要")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="错误信息")


class AiAgentExecution(Base, AuditMixin):
    __tablename__ = "ai_agent_execution"
    __table_args__ = {"comment": "Agent执行记录"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="UUID")
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="任务ID")
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="Agent名称")
    step_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="步骤序号")
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="工具名")
    input_summary: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="入参摘要")
    output_summary: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="出参摘要")
    sql_text_masked: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="脱敏SQL")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="耗时毫秒")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success", comment="状态")
