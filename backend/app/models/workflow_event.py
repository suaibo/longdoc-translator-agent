from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WorkflowEvent(Base):
    __tablename__ = "workflow_event"
    __table_args__ = (
        Index("idx_workflow_event_job_time", "job_id", "created_at"),
        Index("idx_workflow_event_node", "job_id", "node"),
        Index("idx_workflow_event_job_seq", "job_id", "event_seq", unique=True),
    )

    event_id: Mapped[str] = mapped_column(primary_key=True)
    event_seq: Mapped[int] = mapped_column(
        BigInteger, server_default=text("nextval('workflow_event_event_seq_seq')")
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("translation_job.job_id", ondelete="CASCADE")
    )
    node: Mapped[str]
    event_type: Mapped[str]
    status: Mapped[str]
    message: Mapped[str | None]
    elapsed_ms: Mapped[int | None]
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    job = relationship("TranslationJob", back_populates="events")
