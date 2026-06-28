"""Add style preview, model selection, edit versions and SSE sequence.

Revision ID: 20260628_0009
Revises: 20260625_0008
Create Date: 2026-06-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260628_0009"
down_revision: str | None = "20260625_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("translation_job", sa.Column("selected_model", sa.String()))
    op.add_column("translation_job", sa.Column("style_preset", sa.String()))
    op.add_column("translation_job", sa.Column("style_prompt", sa.Text()))
    op.add_column(
        "translation_job",
        sa.Column("style_confirmed_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "translation_job",
        sa.Column(
            "outputs_stale",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("translation_job", "outputs_stale", server_default=None)

    op.create_table(
        "pretranslation_preview",
        sa.Column("preview_id", sa.String(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("translation_job.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column(
            "sample_chunk_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("translated_text", sa.Text(), nullable=False),
        sa.Column("style_prompt", sa.Text()),
        sa.Column("selected_model", sa.String()),
        sa.Column("status", sa.String(), nullable=False, server_default="DRAFT"),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "idx_pretranslation_preview_job",
        "pretranslation_preview",
        ["job_id", "attempt_no"],
    )

    op.create_table(
        "chunk_translation_version",
        sa.Column("version_id", sa.String(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("translation_job.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            sa.String(),
            sa.ForeignKey("document_chunk.chunk_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("translated_text", sa.Text(), nullable=False),
        sa.Column("edit_note", sa.Text()),
        sa.Column(
            "created_by_user_id",
            sa.String(),
            sa.ForeignKey("user_account.user_id", ondelete="SET NULL"),
        ),
        sa.Column("model", sa.String()),
        sa.Column("prompt_version", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("chunk_id", "version_no", name="uq_chunk_version_no"),
    )
    op.create_index(
        "idx_chunk_translation_version_job",
        "chunk_translation_version",
        ["job_id", "created_at"],
    )
    op.create_index(
        "idx_chunk_translation_version_chunk",
        "chunk_translation_version",
        ["chunk_id", "version_no"],
    )
    op.execute(
        """
        INSERT INTO chunk_translation_version
            (version_id, job_id, chunk_id, version_no, source_type,
             translated_text, edit_note, created_by_user_id, model,
             prompt_version, created_at)
        SELECT
            'ver_' || md5(c.chunk_id || ':1'),
            c.job_id,
            c.chunk_id,
            1,
            'LLM_TRANSLATION',
            c.translated_text,
            'migration baseline',
            NULL,
            NULL,
            j.prompt_version,
            COALESCE(c.translated_at, c.updated_at, j.updated_at, now())
        FROM document_chunk c
        JOIN translation_job j ON j.job_id = c.job_id
        WHERE c.translated_text IS NOT NULL
        """
    )

    op.execute("CREATE SEQUENCE IF NOT EXISTS workflow_event_event_seq_seq")
    op.add_column("workflow_event", sa.Column("event_seq", sa.BigInteger()))
    op.execute(
        """
        UPDATE workflow_event
        SET event_seq = nextval('workflow_event_event_seq_seq')
        WHERE event_seq IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_event
        ALTER COLUMN event_seq SET DEFAULT nextval('workflow_event_event_seq_seq')
        """
    )
    op.execute(
        """
        SELECT setval(
            'workflow_event_event_seq_seq',
            GREATEST(
                COALESCE((SELECT MAX(event_seq) FROM workflow_event), 0),
                1
            )
        )
        """
    )
    op.alter_column("workflow_event", "event_seq", nullable=False)
    op.execute(
        """
        ALTER SEQUENCE workflow_event_event_seq_seq
        OWNED BY workflow_event.event_seq
        """
    )
    op.create_index(
        "idx_workflow_event_job_seq",
        "workflow_event",
        ["job_id", "event_seq"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_workflow_event_job_seq", table_name="workflow_event")
    op.drop_column("workflow_event", "event_seq")
    op.execute("DROP SEQUENCE IF EXISTS workflow_event_event_seq_seq")
    op.drop_index(
        "idx_chunk_translation_version_chunk",
        table_name="chunk_translation_version",
    )
    op.drop_index(
        "idx_chunk_translation_version_job",
        table_name="chunk_translation_version",
    )
    op.drop_table("chunk_translation_version")
    op.drop_index(
        "idx_pretranslation_preview_job",
        table_name="pretranslation_preview",
    )
    op.drop_table("pretranslation_preview")
    op.drop_column("translation_job", "outputs_stale")
    op.drop_column("translation_job", "style_confirmed_at")
    op.drop_column("translation_job", "style_prompt")
    op.drop_column("translation_job", "style_preset")
    op.drop_column("translation_job", "selected_model")
