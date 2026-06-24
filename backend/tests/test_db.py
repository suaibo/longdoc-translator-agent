from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.translation_job import TranslationJob


def make_job(job_id: str, status: str = "UPLOADED") -> TranslationJob:
    now = datetime.now(timezone.utc)
    return TranslationJob(
        job_id=job_id,
        original_filename="paper.md",
        original_file_path=f"storage/uploads/{job_id}/paper.md",
        parsed_markdown_path=None,
        mode="paper",
        status=status,
        current_stage="uploaded",
        created_at=now,
        updated_at=now,
    )


def test_alembic_creates_core_tables(db_session: Session) -> None:
    tables = set(inspect(db_session.bind).get_table_names())
    assert {
        "translation_job",
        "document_chunk",
        "term_entry",
        "agent_checkpoint",
        "translation_metric",
        "risk_item",
        "workflow_event",
        "review_request",
        "story_memory",
        "chapter_memory",
        "alembic_version",
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
    }.issubset(tables)


def test_document_chunk_unique_job_index_constraint(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(make_job("job_chunk_constraint", status="COMPLETED"))
    db_session.add_all(
        [
            DocumentChunk(
                chunk_id="chunk_1",
                job_id="job_chunk_constraint",
                chunk_index=0,
                section_title="Abstract",
                source_text="A",
                created_at=now,
                updated_at=now,
            ),
            DocumentChunk(
                chunk_id="chunk_2",
                job_id="job_chunk_constraint",
                chunk_index=0,
                section_title="Abstract",
                source_text="B",
                created_at=now,
                updated_at=now,
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_only_one_active_job_is_allowed(db_session: Session) -> None:
    db_session.add(make_job("job_active_1"))
    db_session.commit()
    db_session.add(make_job("job_active_2"))

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_jsonb_boolean_and_timezone_types(db_session: Session) -> None:
    result = db_session.execute(
        text(
            """
            SELECT
                data_type
            FROM information_schema.columns
            WHERE table_name = 'document_chunk'
              AND column_name IN ('source_block_ids', 'has_risk', 'created_at')
            ORDER BY column_name
            """
        )
    ).scalars()

    assert set(result) == {
        "boolean",
        "jsonb",
        "timestamp with time zone",
    }
