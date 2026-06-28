from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ChunkTranslationVersion(Base):
    __tablename__ = "chunk_translation_version"
    __table_args__ = (
        UniqueConstraint("chunk_id", "version_no", name="uq_chunk_version_no"),
        Index("idx_chunk_translation_version_job", "job_id", "created_at"),
        Index("idx_chunk_translation_version_chunk", "chunk_id", "version_no"),
    )

    version_id: Mapped[str] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("translation_job.job_id", ondelete="CASCADE")
    )
    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("document_chunk.chunk_id", ondelete="CASCADE")
    )
    version_no: Mapped[int]
    source_type: Mapped[str]
    translated_text: Mapped[str]
    edit_note: Mapped[str | None]
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("user_account.user_id", ondelete="SET NULL")
    )
    model: Mapped[str | None]
    prompt_version: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    job = relationship("TranslationJob", back_populates="chunk_versions")
    chunk = relationship("DocumentChunk", back_populates="versions")
