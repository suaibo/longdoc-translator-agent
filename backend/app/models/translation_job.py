from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TranslationJob(Base):
    __tablename__ = "translation_job"
    __table_args__ = (
        Index("idx_translation_job_status", "status"),
        Index("idx_translation_job_created_at", "created_at"),
    )

    job_id: Mapped[str] = mapped_column(primary_key=True)
    original_filename: Mapped[str]
    original_file_path: Mapped[str]
    parsed_markdown_path: Mapped[str | None]
    mode: Mapped[str] = mapped_column(default="paper")
    status: Mapped[str]
    current_stage: Mapped[str]
    total_chunks: Mapped[int] = mapped_column(default=0)
    completed_chunks: Mapped[int] = mapped_column(default=0)
    progress_percent: Mapped[float] = mapped_column(default=0)
    error_code: Mapped[str | None]
    error_message: Mapped[str | None]
    created_at: Mapped[str]
    updated_at: Mapped[str]
    started_at: Mapped[str | None]
    completed_at: Mapped[str | None]
    cancelled_at: Mapped[str | None]

    chunks = relationship("DocumentChunk", back_populates="job", cascade="all, delete-orphan")
    terms = relationship("TermEntry", back_populates="job", cascade="all, delete-orphan")
    checkpoints = relationship("AgentCheckpoint", back_populates="job", cascade="all, delete-orphan")
    metrics = relationship("TranslationMetric", back_populates="job", cascade="all, delete-orphan")
    risks = relationship("RiskItem", back_populates="job", cascade="all, delete-orphan")

