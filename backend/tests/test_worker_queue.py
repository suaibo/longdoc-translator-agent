from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from app.models.job_queue import JobQueue
from app.models.translation_job import TranslationJob
from app.services.worker_service import WorkerService


def test_worker_claims_postgres_queue_item(
    db_session: Session, monkeypatch
) -> None:
    now = datetime.now(timezone.utc)
    job = TranslationJob(
        job_id="job_queue_test",
        original_filename="paper.md",
        original_file_path="paper.md",
        mode="paper",
        status="UPLOADED",
        current_stage="uploaded",
        created_at=now,
        updated_at=now,
    )
    db_session.add(job)
    db_session.commit()
    factory = sessionmaker(
        bind=db_session.get_bind(),
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    monkeypatch.setattr("app.services.worker_service.SessionLocal", factory)
    calls = []
    worker = WorkerService()
    worker.runner = type(
        "Runner",
        (),
        {"run": lambda self, job_id, payload: calls.append((job_id, payload))},
    )()

    worker.enqueue(job.job_id, {"approved": True}, priority=5)
    assert worker.run_once()

    assert calls == [(job.job_id, {"approved": True})]
    db_session.expire_all()
    assert db_session.get(JobQueue, job.job_id) is None
