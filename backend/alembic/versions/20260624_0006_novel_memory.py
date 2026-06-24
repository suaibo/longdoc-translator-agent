"""Add novel entity and chapter memory.

Revision ID: 20260624_0006
Revises: 20260624_0005
Create Date: 2026-06-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260624_0006"
down_revision: str | None = "20260624_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "story_memory",
        sa.Column("memory_id", sa.String(), primary_key=True),
        sa.Column("job_id", sa.String(), sa.ForeignKey("translation_job.job_id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("translated_name", sa.String(), nullable=False),
        sa.Column("note", sa.String()),
        sa.Column("first_seen_chunk", sa.Integer(), nullable=False),
        sa.Column("last_seen_chunk", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", "entity_type", "source_name", name="uq_story_memory_entity"),
    )
    op.create_index("idx_story_memory_job", "story_memory", ["job_id"])
    op.create_table(
        "chapter_memory",
        sa.Column("chapter_memory_id", sa.String(), primary_key=True),
        sa.Column("job_id", sa.String(), sa.ForeignKey("translation_job.job_id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_key", sa.String(), nullable=False),
        sa.Column("section_path", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", "section_key", name="uq_chapter_memory_section"),
    )


def downgrade() -> None:
    op.drop_table("chapter_memory")
    op.drop_table("story_memory")
