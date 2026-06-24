"""Add workflow events and task budgets.

Revision ID: 20260624_0003
Revises: 20260624_0002
Create Date: 2026-06-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260624_0003"
down_revision: str | None = "20260624_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "translation_job",
        sa.Column(
            "max_token_budget",
            sa.Integer(),
            nullable=False,
            server_default="2000000",
        ),
    )
    op.add_column(
        "translation_job",
        sa.Column(
            "max_cost_usd", sa.Float(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "translation_metric",
        sa.Column(
            "estimated_cost_usd", sa.Float(), nullable=False, server_default="0"
        ),
    )
    op.create_table(
        "workflow_event",
        sa.Column("event_id", sa.String(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("translation_job.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("message", sa.String()),
        sa.Column("elapsed_ms", sa.Integer()),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_workflow_event_job_time",
        "workflow_event",
        ["job_id", "created_at"],
    )
    op.create_index(
        "idx_workflow_event_node", "workflow_event", ["job_id", "node"]
    )


def downgrade() -> None:
    op.drop_table("workflow_event")
    op.drop_column("translation_metric", "estimated_cost_usd")
    op.drop_column("translation_job", "max_cost_usd")
    op.drop_column("translation_job", "max_token_budget")
