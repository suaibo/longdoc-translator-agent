"""Replace single active job constraint with a leased queue.

Revision ID: 20260624_0007
Revises: 20260624_0006
Create Date: 2026-06-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260624_0007"
down_revision: str | None = "20260624_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_translation_job_one_active", table_name="translation_job")
    op.create_table(
        "job_queue",
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("translation_job.job_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="QUEUED"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resume_payload", postgresql.JSONB()),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_job_queue_claim",
        "job_queue",
        ["status", "available_at", "priority"],
    )


def downgrade() -> None:
    op.drop_table("job_queue")
    op.create_index(
        "uq_translation_job_one_active",
        "translation_job",
        [sa.text("(1)")],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('UPLOADED', 'PARSED', 'WAITING_TERM_REVIEW', "
            "'WAITING_RISK_REVIEW', 'WAITING_CHAPTER_REVIEW', 'TRANSLATING')"
        ),
    )
