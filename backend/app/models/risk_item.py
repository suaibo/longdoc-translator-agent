from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RiskItem(Base):
    __tablename__ = "risk_item"
    __table_args__ = (
        Index("idx_risk_item_job", "job_id"),
        Index("idx_risk_item_chunk", "chunk_id"),
    )

    risk_id: Mapped[str] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("translation_job.job_id", ondelete="CASCADE")
    )
    chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_chunk.chunk_id", ondelete="SET NULL")
    )
    risk_type: Mapped[str]
    severity: Mapped[str] = mapped_column(default="MEDIUM")
    message: Mapped[str]
    source_excerpt: Mapped[str | None]
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    job = relationship("TranslationJob", back_populates="risks")
    chunk = relationship("DocumentChunk", back_populates="risks")
