from datetime import datetime, timezone

import pytest
from langgraph.errors import GraphInterrupt
from sqlalchemy.orm import Session, sessionmaker

from app.agent.nodes import WorkflowNodes
from app.models.document_chunk import DocumentChunk
from app.models.risk_item import RiskItem
from app.models.translation_job import TranslationJob
from app.services.review_service import ReviewService


def _job(job_id: str, *, risk: bool = False, chapter: bool = False) -> TranslationJob:
    now = datetime.now(timezone.utc)
    return TranslationJob(
        job_id=job_id,
        original_filename="paper.md",
        original_file_path="paper.md",
        mode="paper",
        status="TRANSLATING",
        current_stage="mark_risks",
        require_high_risk_review=risk,
        require_chapter_review=chapter,
        created_at=now,
        updated_at=now,
    )


def _chunk(job_id: str, chunk_id: str) -> DocumentChunk:
    now = datetime.now(timezone.utc)
    return DocumentChunk(
        chunk_id=chunk_id,
        job_id=job_id,
        chunk_index=0,
        section_title="Methods",
        section_path=["Methods"],
        source_text="A",
        translated_text="甲",
        status="COMPLETED",
        created_at=now,
        updated_at=now,
    )


def test_high_risk_review_creates_interrupt(
    db_session: Session, monkeypatch
) -> None:
    job = _job("job_risk_review", risk=True)
    chunk = _chunk(job.job_id, "chunk_risk_review")
    db_session.add_all([job, chunk])
    db_session.flush()
    db_session.add(
        RiskItem(
            risk_id="risk_high",
            job_id=job.job_id,
            chunk_id=chunk.chunk_id,
            risk_type="OMISSION",
            severity="HIGH",
            message="possible omission",
            metadata_json={},
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()
    factory = sessionmaker(
        bind=db_session.get_bind(),
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    monkeypatch.setattr("app.agent.nodes.SessionLocal", factory)
    monkeypatch.setattr("app.agent.nodes.interrupt", _raise_interrupt)

    with pytest.raises(GraphInterrupt):
        WorkflowNodes().interrupt_for_high_risk_review(
            {"job_id": job.job_id, "current_chunk_id": chunk.chunk_id}
        )

    db_session.expire_all()
    assert db_session.get(TranslationJob, job.job_id).status == "WAITING_RISK_REVIEW"
    assert ReviewService(db_session).list_reviews(job.job_id)[0].status == "PENDING"


def test_chapter_review_only_interrupts_at_section_end(
    db_session: Session, monkeypatch
) -> None:
    job = _job("job_chapter_review", chapter=True)
    chunk = _chunk(job.job_id, "chunk_chapter_review")
    db_session.add_all([job, chunk])
    db_session.commit()
    factory = sessionmaker(
        bind=db_session.get_bind(),
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    monkeypatch.setattr("app.agent.nodes.SessionLocal", factory)
    monkeypatch.setattr("app.agent.nodes.interrupt", _raise_interrupt)

    with pytest.raises(GraphInterrupt):
        WorkflowNodes().interrupt_for_chapter_review(
            {"job_id": job.job_id, "current_chunk_id": chunk.chunk_id}
        )

    db_session.expire_all()
    assert (
        db_session.get(TranslationJob, job.job_id).status
        == "WAITING_CHAPTER_REVIEW"
    )


def _raise_interrupt(_payload) -> None:
    raise GraphInterrupt()
