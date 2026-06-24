"""Create the PostgreSQL MVP schema.

Revision ID: 20260624_0001
Revises:
Create Date: 2026-06-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260624_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "translation_job",
        sa.Column("job_id", sa.String(), primary_key=True),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("original_file_path", sa.String(), nullable=False),
        sa.Column("parsed_markdown_path", sa.String(), nullable=True),
        sa.Column("mode", sa.String(), nullable=False, server_default="paper"),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_stage", sa.String(), nullable=False),
        sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_translation_job_status", "translation_job", ["status"])
    op.create_index("idx_translation_job_created_at", "translation_job", ["created_at"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_translation_job_one_active
        ON translation_job ((1))
        WHERE status IN ('UPLOADED', 'PARSED', 'WAITING_TERM_REVIEW', 'TRANSLATING')
        """
    )

    op.create_table(
        "document_chunk",
        sa.Column("chunk_id", sa.String(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("translation_job.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section_title", sa.String(), nullable=True),
        sa.Column("chunk_type", sa.String(), nullable=False, server_default="TEXT"),
        sa.Column("source_text", sa.String(), nullable=False),
        sa.Column(
            "source_block_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "structure_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("translated_text", sa.String(), nullable=True),
        sa.Column("context_summary", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("has_risk", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("risk_summary", sa.String(), nullable=True),
        sa.Column("token_estimate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("translated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "job_id", "chunk_index", name="uq_document_chunk_job_index"
        ),
    )
    op.create_index("idx_document_chunk_job", "document_chunk", ["job_id"])
    op.create_index(
        "idx_document_chunk_status", "document_chunk", ["job_id", "status"]
    )

    op.create_table(
        "term_entry",
        sa.Column("term_id", sa.String(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("translation_job.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_term", sa.String(), nullable=False),
        sa.Column("suggested_translation", sa.String(), nullable=False),
        sa.Column("confirmed_translation", sa.String(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "job_id", "source_term", name="uq_term_entry_job_source"
        ),
    )
    op.create_index("idx_term_entry_job", "term_entry", ["job_id"])

    op.create_table(
        "agent_checkpoint",
        sa.Column("checkpoint_id", sa.String(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("translation_job.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("current_node", sa.String(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        sa.Column("state_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_agent_checkpoint_job",
        "agent_checkpoint",
        ["job_id", "created_at"],
    )

    op.create_table(
        "translation_metric",
        sa.Column("metric_id", sa.String(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("translation_job.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            sa.String(),
            sa.ForeignKey("document_chunk.chunk_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "completion_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_translation_metric_job", "translation_metric", ["job_id"])
    op.create_index(
        "idx_translation_metric_chunk", "translation_metric", ["chunk_id"]
    )

    op.create_table(
        "risk_item",
        sa.Column("risk_id", sa.String(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("translation_job.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            sa.String(),
            sa.ForeignKey("document_chunk.chunk_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("risk_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False, server_default="MEDIUM"),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("source_excerpt", sa.String(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_risk_item_job", "risk_item", ["job_id"])
    op.create_index("idx_risk_item_chunk", "risk_item", ["chunk_id"])


def downgrade() -> None:
    op.drop_table("risk_item")
    op.drop_table("translation_metric")
    op.drop_table("agent_checkpoint")
    op.drop_table("term_entry")
    op.drop_table("document_chunk")
    op.drop_table("translation_job")
