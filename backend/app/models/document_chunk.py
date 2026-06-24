from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunk"
    __table_args__ = (
        UniqueConstraint("job_id", "chunk_index", name="uq_document_chunk_job_index"),
        Index("idx_document_chunk_job", "job_id"),
        Index("idx_document_chunk_status", "job_id", "status"),
    )

    chunk_id: Mapped[str] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("translation_job.job_id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int]
    section_title: Mapped[str | None]
    chunk_type: Mapped[str] = mapped_column(default="TEXT")
    source_text: Mapped[str]
    source_block_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    structure_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    section_path: Mapped[list[str]] = mapped_column(JSONB, default=list)
    boundary_reason: Mapped[str | None]
    boundary_score: Mapped[float | None]
    semantic_topic: Mapped[str | None]
    translated_text: Mapped[str | None]
    context_summary: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="PENDING")
    has_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_summary: Mapped[str | None]
    token_estimate: Mapped[int] = mapped_column(default=0)
    revision_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    translated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job = relationship("TranslationJob", back_populates="chunks")
    metrics = relationship("TranslationMetric", back_populates="chunk")
    risks = relationship("RiskItem", back_populates="chunk")
