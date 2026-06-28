from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PretranslationPreview(Base):
    __tablename__ = "pretranslation_preview"
    __table_args__ = (
        Index("idx_pretranslation_preview_job", "job_id", "attempt_no"),
    )

    preview_id: Mapped[str] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("translation_job.job_id", ondelete="CASCADE")
    )
    attempt_no: Mapped[int]
    sample_chunk_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    source_text: Mapped[str]
    translated_text: Mapped[str]
    style_prompt: Mapped[str | None]
    selected_model: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="DRAFT")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job = relationship("TranslationJob", back_populates="pretranslation_previews")
