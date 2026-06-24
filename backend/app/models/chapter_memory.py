from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ChapterMemory(Base):
    __tablename__ = "chapter_memory"
    __table_args__ = (
        UniqueConstraint("job_id", "section_key", name="uq_chapter_memory_section"),
    )

    chapter_memory_id: Mapped[str] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("translation_job.job_id", ondelete="CASCADE")
    )
    section_key: Mapped[str]
    section_path: Mapped[list[str]] = mapped_column(JSONB, default=list)
    summary: Mapped[str]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    job = relationship("TranslationJob", back_populates="chapter_memories")
