from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ReviewRequest(Base):
    __tablename__ = "review_request"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "review_type",
            "subject_id",
            name="uq_review_request_subject",
        ),
        Index("idx_review_request_job_status", "job_id", "status"),
    )

    review_id: Mapped[str] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("translation_job.job_id", ondelete="CASCADE")
    )
    review_type: Mapped[str]
    subject_id: Mapped[str]
    status: Mapped[str]
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    resolution_note: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job = relationship("TranslationJob", back_populates="reviews")
