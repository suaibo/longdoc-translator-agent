import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.init_db import init_db
from app.models.document_chunk import DocumentChunk
from app.models.translation_job import TranslationJob


@event.listens_for(Engine, "connect")
def set_sqlite_fk(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    return sessionmaker(bind=engine, future=True)()


def test_init_db_creates_core_tables() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)

    tables = set(inspect(engine).get_table_names())
    assert {
        "translation_job",
        "document_chunk",
        "term_entry",
        "agent_checkpoint",
        "translation_metric",
        "risk_item",
    }.issubset(tables)


def test_document_chunk_unique_job_index_constraint() -> None:
    db = make_session()
    job = TranslationJob(
        job_id="job_test",
        original_filename="paper.md",
        original_file_path="storage/uploads/job_test/paper.md",
        parsed_markdown_path=None,
        mode="paper",
        status="UPLOADED",
        current_stage="uploaded",
        created_at="2026-06-23T00:00:00+08:00",
        updated_at="2026-06-23T00:00:00+08:00",
    )
    db.add(job)
    db.add_all(
        [
            DocumentChunk(
                chunk_id="chunk_1",
                job_id="job_test",
                chunk_index=0,
                section_title="Abstract",
                source_text="A",
                created_at="2026-06-23T00:00:00+08:00",
                updated_at="2026-06-23T00:00:00+08:00",
            ),
            DocumentChunk(
                chunk_id="chunk_2",
                job_id="job_test",
                chunk_index=0,
                section_title="Abstract",
                source_text="B",
                created_at="2026-06-23T00:00:00+08:00",
                updated_at="2026-06-23T00:00:00+08:00",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db.commit()
