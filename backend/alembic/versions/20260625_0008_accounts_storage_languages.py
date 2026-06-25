"""Add accounts, job ownership, languages and durable storage metadata.

Revision ID: 20260625_0008
Revises: 20260624_0007
Create Date: 2026-06-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260625_0008"
down_revision: str | None = "20260624_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_account",
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_user_account_username", "user_account", ["username"], unique=True)
    op.create_table(
        "auth_session",
        sa.Column("session_id", sa.String(), primary_key=True),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("user_account.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_auth_session_user", "auth_session", ["user_id"])
    op.create_index("idx_auth_session_expires", "auth_session", ["expires_at"])
    op.execute(
        """
        INSERT INTO user_account
            (user_id, username, password_hash, is_active, created_at, updated_at)
        VALUES
            ('usr_legacy', 'legacy_local', 'disabled', false, now(), now())
        """
    )
    op.add_column(
        "translation_job",
        sa.Column("user_id", sa.String(), nullable=False, server_default="usr_legacy"),
    )
    op.create_foreign_key(
        "fk_translation_job_user",
        "translation_job",
        "user_account",
        ["user_id"],
        ["user_id"],
        ondelete="RESTRICT",
    )
    op.alter_column("translation_job", "user_id", server_default=None)
    op.add_column("translation_job", sa.Column("source_storage_key", sa.String()))
    op.add_column("translation_job", sa.Column("output_storage_prefix", sa.String()))
    op.add_column("translation_job", sa.Column("source_language", sa.String()))
    op.add_column(
        "translation_job",
        sa.Column("target_language", sa.String(), nullable=False, server_default="zh"),
    )
    op.add_column("translation_job", sa.Column("eta_seconds", sa.Integer()))
    op.add_column(
        "translation_job",
        sa.Column(
            "has_unresolved_risks",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "translation_job", sa.Column("retention_expires_at", sa.DateTime(timezone=True))
    )
    op.create_index(
        "idx_translation_job_user_created",
        "translation_job",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_translation_job_user_created", table_name="translation_job")
    op.drop_column("translation_job", "retention_expires_at")
    op.drop_column("translation_job", "has_unresolved_risks")
    op.drop_column("translation_job", "eta_seconds")
    op.drop_column("translation_job", "target_language")
    op.drop_column("translation_job", "source_language")
    op.drop_column("translation_job", "output_storage_prefix")
    op.drop_column("translation_job", "source_storage_key")
    op.drop_constraint("fk_translation_job_user", "translation_job", type_="foreignkey")
    op.drop_column("translation_job", "user_id")
    op.drop_table("auth_session")
    op.drop_table("user_account")
