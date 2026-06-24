from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TermEntry(Base):
    __tablename__ = "term_entry"
    __table_args__ = (
        UniqueConstraint("job_id", "source_term", name="uq_term_entry_job_source"),
        Index("idx_term_entry_job", "job_id"),
    )

    term_id: Mapped[str] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("translation_job.job_id", ondelete="CASCADE")
    )
    source_term: Mapped[str]
    suggested_translation: Mapped[str]
    confirmed_translation: Mapped[str | None]
    note: Mapped[str | None]
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    job = relationship("TranslationJob", back_populates="terms")
