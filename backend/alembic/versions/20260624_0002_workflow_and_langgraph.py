"""Add workflow metadata, explainable chunks, and LangGraph checkpoints.

Revision ID: 20260624_0002
Revises: 20260624_0001
Create Date: 2026-06-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260624_0002"
down_revision: str | None = "20260624_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("translation_job", sa.Column("document_ir_path", sa.String()))
    op.add_column("translation_job", sa.Column("document_ir_version", sa.String()))
    op.add_column("translation_job", sa.Column("output_manifest_path", sa.String()))
    op.add_column(
        "translation_job",
        sa.Column("ocr_mode", sa.String(), nullable=False, server_default="auto"),
    )
    op.add_column(
        "translation_job",
        sa.Column("workflow_version", sa.String(), nullable=False, server_default="1"),
    )
    op.add_column(
        "translation_job",
        sa.Column("prompt_version", sa.String(), nullable=False, server_default="1"),
    )
    op.add_column(
        "translation_job",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "document_chunk",
        sa.Column(
            "section_path",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("document_chunk", sa.Column("boundary_reason", sa.String()))
    op.add_column("document_chunk", sa.Column("boundary_score", sa.Float()))
    op.add_column("document_chunk", sa.Column("semantic_topic", sa.String()))

    # These are the current tables required by langgraph-checkpoint-postgres 3.1.
    op.create_table(
        "checkpoints",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), nullable=False, server_default=""),
        sa.Column("checkpoint_id", sa.Text(), nullable=False),
        sa.Column("parent_checkpoint_id", sa.Text()),
        sa.Column("type", sa.Text()),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id"),
    )
    op.create_table(
        "checkpoint_blobs",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), nullable=False, server_default=""),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("blob", sa.LargeBinary()),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "channel", "version"),
    )
    op.create_table(
        "checkpoint_writes",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), nullable=False, server_default=""),
        sa.Column("checkpoint_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("type", sa.Text()),
        sa.Column("blob", sa.LargeBinary(), nullable=False),
        sa.Column("task_path", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint(
            "thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"
        ),
    )
    op.create_index("checkpoints_thread_id_idx", "checkpoints", ["thread_id"])
    op.create_index(
        "checkpoint_blobs_thread_id_idx", "checkpoint_blobs", ["thread_id"]
    )
    op.create_index(
        "checkpoint_writes_thread_id_idx", "checkpoint_writes", ["thread_id"]
    )


def downgrade() -> None:
    op.drop_table("checkpoint_writes")
    op.drop_table("checkpoint_blobs")
    op.drop_table("checkpoints")
    op.drop_column("document_chunk", "semantic_topic")
    op.drop_column("document_chunk", "boundary_score")
    op.drop_column("document_chunk", "boundary_reason")
    op.drop_column("document_chunk", "section_path")
    op.drop_column("translation_job", "retry_count")
    op.drop_column("translation_job", "prompt_version")
    op.drop_column("translation_job", "workflow_version")
    op.drop_column("translation_job", "ocr_mode")
    op.drop_column("translation_job", "output_manifest_path")
    op.drop_column("translation_job", "document_ir_version")
    op.drop_column("translation_job", "document_ir_path")
