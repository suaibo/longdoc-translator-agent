from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session, sessionmaker

from app.models.job_queue import JobQueue
from app.models.translation_job import TranslationJob
from app.models.user_account import UserAccount
from app.services.worker_service import WorkerService


def test_worker_claims_postgres_queue_item(db_session: Session, monkeypatch) -> None:
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


def test_resume_restores_pre_translation_stage_status(
    db_session: Session, monkeypatch
) -> None:
    now = datetime.now(timezone.utc)
    job = TranslationJob(
        job_id="job_resume_split",
        original_filename="paper.pdf",
        original_file_path="paper.pdf",
        mode="paper",
        status="FAILED",
        current_stage="split_sections",
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
    worker = WorkerService()
    queued: list[str] = []
    monkeypatch.setattr(worker, "enqueue", lambda job_id: queued.append(job_id))

    worker.resume(job.job_id)

    db_session.expire_all()
    assert db_session.get(TranslationJob, job.job_id).status == "PARSED"
    assert queued == [job.job_id]


def test_worker_does_not_claim_sixth_active_job_for_same_user(
    db_session: Session, monkeypatch
) -> None:
    now = datetime.now(timezone.utc)
    user = UserAccount(
        user_id="usr_concurrency",
        username="concurrency-user",
        password_hash="disabled",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(user)
    for index in range(6):
        job = TranslationJob(
            job_id=f"job_concurrency_{index}",
            user_id=user.user_id,
            original_filename=f"{index}.md",
            original_file_path=f"{index}.md",
            mode="paper",
            status="UPLOADED",
            current_stage="uploaded",
            created_at=now + timedelta(milliseconds=index),
            updated_at=now,
        )
        db_session.add(job)
        db_session.add(
            JobQueue(
                job_id=job.job_id,
                status="LEASED" if index < 5 else "QUEUED",
                priority=0,
                available_at=now,
                lease_owner="other-worker" if index < 5 else None,
                lease_expires_at=(now + timedelta(minutes=5)) if index < 5 else None,
                created_at=now + timedelta(milliseconds=index),
                updated_at=now,
            )
        )
    db_session.commit()
    factory = sessionmaker(
        bind=db_session.get_bind(),
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    monkeypatch.setattr("app.services.worker_service.SessionLocal", factory)
    worker = WorkerService()
    worker.user_max_concurrency = 5
    try:
        assert worker._claim_next() is None
    finally:
        worker.shutdown()
