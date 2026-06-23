from sqlalchemy import ForeignKey, Index, UniqueConstraint
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
    job_id: Mapped[str] = mapped_column(ForeignKey("translation_job.job_id", ondelete="CASCADE"))
    chunk_index: Mapped[int]
    section_title: Mapped[str | None]
    source_text: Mapped[str]
    translated_text: Mapped[str | None]
    context_summary: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="PENDING")
    has_risk: Mapped[int] = mapped_column(default=0)
    risk_summary: Mapped[str | None]
    token_estimate: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str]
    updated_at: Mapped[str]
    translated_at: Mapped[str | None]

    job = relationship("TranslationJob", back_populates="chunks")
    metrics = relationship("TranslationMetric", back_populates="chunk")
    risks = relationship("RiskItem", back_populates="chunk")

