from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TranslationMetric(Base):
    __tablename__ = "translation_metric"
    __table_args__ = (
        Index("idx_translation_metric_job", "job_id"),
        Index("idx_translation_metric_chunk", "chunk_id"),
    )

    metric_id: Mapped[str] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("translation_job.job_id", ondelete="CASCADE")
    )
    chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_chunk.chunk_id", ondelete="SET NULL")
    )
    provider: Mapped[str | None]
    model: Mapped[str | None]
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    total_tokens: Mapped[int] = mapped_column(default=0)
    elapsed_ms: Mapped[int] = mapped_column(default=0)
    retry_count: Mapped[int] = mapped_column(default=0)
    failed_count: Mapped[int] = mapped_column(default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    job = relationship("TranslationJob", back_populates="metrics")
    chunk = relationship("DocumentChunk", back_populates="metrics")
