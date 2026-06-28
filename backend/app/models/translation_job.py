from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TranslationJob(Base):
    __tablename__ = "translation_job"
    __table_args__ = (
        Index("idx_translation_job_status", "status"),
        Index("idx_translation_job_created_at", "created_at"),
        Index("idx_translation_job_user_created", "user_id", "created_at"),
    )

    job_id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_account.user_id", ondelete="RESTRICT"),
        default="usr_legacy",
    )
    original_filename: Mapped[str]
    original_file_path: Mapped[str]
    parsed_markdown_path: Mapped[str | None]
    document_ir_path: Mapped[str | None]
    document_ir_version: Mapped[str | None]
    output_manifest_path: Mapped[str | None]
    source_storage_key: Mapped[str | None]
    output_storage_prefix: Mapped[str | None]
    mode: Mapped[str] = mapped_column(default="paper")
    ocr_mode: Mapped[str] = mapped_column(default="auto")
    source_language: Mapped[str | None]
    target_language: Mapped[str] = mapped_column(default="zh")
    selected_model: Mapped[str | None]
    style_preset: Mapped[str | None]
    style_prompt: Mapped[str | None]
    style_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    workflow_version: Mapped[str] = mapped_column(default="1")
    prompt_version: Mapped[str] = mapped_column(default="1")
    status: Mapped[str]
    current_stage: Mapped[str]
    total_chunks: Mapped[int] = mapped_column(default=0)
    completed_chunks: Mapped[int] = mapped_column(default=0)
    progress_percent: Mapped[float] = mapped_column(default=0)
    eta_seconds: Mapped[int | None]
    has_unresolved_risks: Mapped[bool] = mapped_column(default=False)
    outputs_stale: Mapped[bool] = mapped_column(default=False)
    error_code: Mapped[str | None]
    error_message: Mapped[str | None]
    retry_count: Mapped[int] = mapped_column(default=0)
    max_token_budget: Mapped[int] = mapped_column(default=2_000_000)
    max_cost_usd: Mapped[float] = mapped_column(default=0)
    require_high_risk_review: Mapped[bool] = mapped_column(default=False)
    require_chapter_review: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    user = relationship("UserAccount", back_populates="jobs")

    chunks = relationship(
        "DocumentChunk", back_populates="job", cascade="all, delete-orphan"
    )
    terms = relationship(
        "TermEntry", back_populates="job", cascade="all, delete-orphan"
    )
    checkpoints = relationship(
        "AgentCheckpoint", back_populates="job", cascade="all, delete-orphan"
    )
    metrics = relationship(
        "TranslationMetric", back_populates="job", cascade="all, delete-orphan"
    )
    risks = relationship("RiskItem", back_populates="job", cascade="all, delete-orphan")
    events = relationship(
        "WorkflowEvent", back_populates="job", cascade="all, delete-orphan"
    )
    reviews = relationship(
        "ReviewRequest", back_populates="job", cascade="all, delete-orphan"
    )
    pretranslation_previews = relationship(
        "PretranslationPreview", back_populates="job", cascade="all, delete-orphan"
    )
    chunk_versions = relationship(
        "ChunkTranslationVersion",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    story_memories = relationship(
        "StoryMemory", back_populates="job", cascade="all, delete-orphan"
    )
    chapter_memories = relationship(
        "ChapterMemory", back_populates="job", cascade="all, delete-orphan"
    )
    queue_item = relationship(
        "JobQueue",
        back_populates="job",
        cascade="all, delete-orphan",
        uselist=False,
    )
