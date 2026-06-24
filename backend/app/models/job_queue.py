from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class JobQueue(Base):
    __tablename__ = "job_queue"
    __table_args__ = (
        Index("idx_job_queue_claim", "status", "available_at", "priority"),
    )

    job_id: Mapped[str] = mapped_column(
        ForeignKey("translation_job.job_id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(default="QUEUED")
    priority: Mapped[int] = mapped_column(default=0)
    resume_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None]
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    job = relationship("TranslationJob", back_populates="queue_item")
