"""Add optional risk and chapter reviews.

Revision ID: 20260624_0004
Revises: 20260624_0003
Create Date: 2026-06-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260624_0004"
down_revision: str | None = "20260624_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "translation_job",
        sa.Column(
            "require_high_risk_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "translation_job",
        sa.Column(
            "require_chapter_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.drop_index("uq_translation_job_one_active", table_name="translation_job")
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
    op.create_table(
        "review_request",
        sa.Column("review_id", sa.String(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("translation_job.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("review_type", sa.String(), nullable=False),
        sa.Column("subject_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("resolution_note", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "job_id",
            "review_type",
            "subject_id",
            name="uq_review_request_subject",
        ),
    )
    op.create_index(
        "idx_review_request_job_status",
        "review_request",
        ["job_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("review_request")
    op.drop_index("uq_translation_job_one_active", table_name="translation_job")
    op.create_index(
        "uq_translation_job_one_active",
        "translation_job",
        [sa.text("(1)")],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('UPLOADED', 'PARSED', 'WAITING_TERM_REVIEW', 'TRANSLATING')"
        ),
    )
    op.drop_column("translation_job", "require_chapter_review")
    op.drop_column("translation_job", "require_high_risk_review")
