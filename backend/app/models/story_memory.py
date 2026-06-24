from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StoryMemory(Base):
    __tablename__ = "story_memory"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "entity_type", "source_name", name="uq_story_memory_entity"
        ),
        Index("idx_story_memory_job", "job_id"),
    )

    memory_id: Mapped[str] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("translation_job.job_id", ondelete="CASCADE")
    )
    entity_type: Mapped[str]
    source_name: Mapped[str]
    translated_name: Mapped[str]
    note: Mapped[str | None]
    first_seen_chunk: Mapped[int]
    last_seen_chunk: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    job = relationship("TranslationJob", back_populates="story_memories")
