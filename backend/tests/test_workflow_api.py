from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.risk_item import RiskItem
from app.models.review_request import ReviewRequest
from app.models.term_entry import TermEntry
from app.models.translation_job import TranslationJob
from app.models.user_account import UserAccount
from app.services.event_service import EventService


def add_job(
    db: Session,
    tmp_path: Path,
    *,
    job_id: str,
    status: str,
) -> TranslationJob:
    source = tmp_path / f"{job_id}.md"
    source.write_text("# Paper", encoding="utf-8")
    now = datetime.now(timezone.utc)
    owner = db.scalar(select(UserAccount).where(UserAccount.username == "testuser"))
    assert owner is not None
    job = TranslationJob(
        job_id=job_id,
        user_id=owner.user_id,
        original_filename="paper.md",
        original_file_path=str(source),
        mode="paper",
        status=status,
        current_stage="test",
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    return job


def test_terms_chunks_and_source_endpoints(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    job = add_job(
        db_session,
        tmp_path,
        job_id="job_workflow_api",
        status="WAITING_TERM_REVIEW",
    )
    now = datetime.now(timezone.utc)
    db_session.add(
        TermEntry(
            term_id="term_api",
            job_id=job.job_id,
            source_term="checkpoint",
            suggested_translation="检查点",
            confirmed_translation=None,
            confirmed=False,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        DocumentChunk(
            chunk_id="chunk_api",
            job_id=job.job_id,
            chunk_index=0,
            section_title="Paper",
            section_path=["Paper"],
            boundary_reason="END_OF_DOCUMENT",
            source_text="checkpoint [1]",
            status="PENDING",
            has_risk=True,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        RiskItem(
            risk_id="risk_api",
            job_id=job.job_id,
            chunk_id="chunk_api",
            risk_type="REFERENCE",
            severity="MEDIUM",
            message="检查引用",
            metadata_json={},
            created_at=now,
        )
    )
    db_session.commit()

    terms = client.get(f"/api/jobs/{job.job_id}/terms")
    chunks = client.get(f"/api/jobs/{job.job_id}/chunks")
    source = client.get(f"/api/jobs/{job.job_id}/source")

    assert terms.status_code == 200
    assert terms.json()["data"][0]["sourceTerm"] == "checkpoint"
    assert chunks.status_code == 200
    assert chunks.json()["data"][0]["sectionPath"] == ["Paper"]
    assert chunks.json()["data"][0]["riskTypes"] == ["REFERENCE"]
    assert source.status_code == 200
    assert source.content == b"# Paper"


def test_confirm_terms_resumes_workflow(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    job = add_job(
        db_session,
        tmp_path,
        job_id="job_confirm_api",
        status="WAITING_TERM_REVIEW",
    )
    now = datetime.now(timezone.utc)
    db_session.add(
        TermEntry(
            term_id="term_confirm",
            job_id=job.job_id,
            source_term="checkpoint",
            suggested_translation="检查点",
            confirmed=False,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()

    response = client.put(
        f"/api/jobs/{job.job_id}/terms",
        json={
            "terms": [
                {
                    "termId": "term_confirm",
                    "confirmedTranslation": "检查点",
                    "note": "固定译名",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "TRANSLATING"
    db_session.refresh(job)
    assert job.status == "TRANSLATING"


def test_outputs_require_completed_status(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    job = add_job(
        db_session,
        tmp_path,
        job_id="job_output_api",
        status="TRANSLATING",
    )
    output_dir = tmp_path / "storage" / "outputs" / job.job_id
    output_dir.mkdir(parents=True)
    (output_dir / "bilingual.md").write_text("content", encoding="utf-8")

    response = client.get(f"/api/jobs/{job.job_id}/outputs/bilingual")
    listing = client.get(f"/api/jobs/{job.job_id}/outputs")

    assert response.status_code == 409
    assert listing.status_code == 200
    assert not any(item["available"] for item in listing.json()["data"])


def test_workflow_events_endpoint(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    job = add_job(
        db_session,
        tmp_path,
        job_id="job_events_api",
        status="COMPLETED",
    )
    EventService(db_session).record(
        job.job_id,
        "translate_chunk",
        "NODE",
        "FAILED",
        message="provider timeout",
        elapsed_ms=1200,
        metadata={"chunkIndex": 2},
    )

    response = client.get(f"/api/jobs/{job.job_id}/events")

    assert response.status_code == 200
    event = response.json()["data"][0]
    assert event["node"] == "translate_chunk"
    assert event["status"] == "FAILED"
    assert event["elapsedMs"] == 1200
    assert event["metadata"] == {"chunkIndex": 2}


def test_review_endpoint_approves_pending_request(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    job = add_job(
        db_session,
        tmp_path,
        job_id="job_review_api",
        status="WAITING_CHAPTER_REVIEW",
    )
    now = datetime.now(timezone.utc)
    db_session.add(
        ReviewRequest(
            review_id="review_api",
            job_id=job.job_id,
            review_type="CHAPTER",
            subject_id="Methods",
            status="PENDING",
            payload_json={"sectionPath": ["Methods"]},
            created_at=now,
        )
    )
    db_session.commit()

    listed = client.get(f"/api/jobs/{job.job_id}/reviews")
    approved = client.post(
        f"/api/jobs/{job.job_id}/reviews/review_api/approve",
        json={"note": "checked"},
    )

    assert listed.status_code == 200
    assert listed.json()["data"][0]["reviewType"] == "CHAPTER"
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "APPROVED"
    db_session.refresh(job)
    assert job.status == "TRANSLATING"
