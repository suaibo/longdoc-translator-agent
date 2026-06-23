from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AgentCheckpoint(Base):
    __tablename__ = "agent_checkpoint"
    __table_args__ = (Index("idx_agent_checkpoint_job", "job_id", "created_at"),)

    checkpoint_id: Mapped[str] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("translation_job.job_id", ondelete="CASCADE"))
    thread_id: Mapped[str]
    current_node: Mapped[str]
    chunk_index: Mapped[int | None]
    state_snapshot: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str]

    job = relationship("TranslationJob", back_populates="checkpoints")

