from datetime import datetime

from sqlalchemy import DateTime, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TranslationJob(Base):
    __tablename__ = "translation_job"
    __table_args__ = (
        Index("idx_translation_job_status", "status"),
        Index("idx_translation_job_created_at", "created_at"),
        Index(
            "uq_translation_job_one_active",
            text("(1)"),
            unique=True,
            postgresql_where=text(
                "status IN ('UPLOADED', 'PARSED', 'WAITING_TERM_REVIEW', "
                "'WAITING_RISK_REVIEW', 'WAITING_CHAPTER_REVIEW', 'TRANSLATING')"
            ),
        ),
    )

    job_id: Mapped[str] = mapped_column(primary_key=True)
    original_filename: Mapped[str]
    original_file_path: Mapped[str]
    parsed_markdown_path: Mapped[str | None]
    document_ir_path: Mapped[str | None]
    document_ir_version: Mapped[str | None]
    output_manifest_path: Mapped[str | None]
    mode: Mapped[str] = mapped_column(default="paper")
    ocr_mode: Mapped[str] = mapped_column(default="auto")
    workflow_version: Mapped[str] = mapped_column(default="1")
    prompt_version: Mapped[str] = mapped_column(default="1")
    status: Mapped[str]
    current_stage: Mapped[str]
    total_chunks: Mapped[int] = mapped_column(default=0)
    completed_chunks: Mapped[int] = mapped_column(default=0)
    progress_percent: Mapped[float] = mapped_column(default=0)
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

    chunks = relationship("DocumentChunk", back_populates="job", cascade="all, delete-orphan")
    terms = relationship("TermEntry", back_populates="job", cascade="all, delete-orphan")
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
