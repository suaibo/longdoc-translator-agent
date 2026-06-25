import logging
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select

from app.agent.runner import WorkflowRunner
from app.core.errors import AppError, ErrorCode
from app.db.session import SessionLocal
from app.models.enums import JobStatus
from app.models.job_queue import JobQueue
from app.models.translation_job import TranslationJob
from app.services.checkpoint_service import CheckpointService

logger = logging.getLogger(__name__)


class WorkerService:
    """PostgreSQL-backed leased worker usable in-process or standalone."""

    def __init__(self, *, poll_seconds: float = 1.0) -> None:
        self.runner = WorkflowRunner()
        self.worker_id = f"worker_{uuid4().hex}"
        self.poll_seconds = poll_seconds
        self.stop_event = Event()
        self.thread: Thread | None = None

    def enqueue(
        self,
        job_id: str,
        resume_payload: dict[str, Any] | None = None,
        priority: int = 0,
    ) -> None:
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            if db.get(TranslationJob, job_id) is None:
                raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
            item = db.get(JobQueue, job_id)
            if item is None:
                item = JobQueue(
                    job_id=job_id,
                    status="QUEUED",
                    priority=priority,
                    resume_payload=resume_payload,
                    available_at=now,
                    created_at=now,
                    updated_at=now,
                )
                db.add(item)
            else:
                item.status = "QUEUED"
                item.priority = max(item.priority, priority)
                item.resume_payload = resume_payload
                item.available_at = now
                item.lease_owner = None
                item.lease_expires_at = None
                item.updated_at = now
            db.commit()

    def recover(self) -> None:
        with SessionLocal() as db:
            jobs = list(
                db.scalars(
                    select(TranslationJob).where(
                        TranslationJob.status.in_(
                            [
                                JobStatus.UPLOADED.value,
                                JobStatus.PARSED.value,
                                JobStatus.TRANSLATING.value,
                            ]
                        )
                    )
                )
            )
            queued_ids = set(db.scalars(select(JobQueue.job_id)))
        for job in jobs:
            if job.job_id not in queued_ids:
                self.enqueue(job.job_id)
        self.start_background()

    def start_background(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = Thread(
            target=self.run_forever,
            name="longdoc-db-worker",
            daemon=True,
        )
        self.thread.start()

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            if not self.run_once():
                self.stop_event.wait(self.poll_seconds)

    def run_once(self) -> bool:
        claimed = self._claim_next()
        if claimed is None:
            return False
        job_id, payload = claimed
        self._execute(job_id, payload)
        return True

    def resume(self, job_id: str) -> None:
        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job is None:
                raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
            if job.status != JobStatus.FAILED.value:
                raise AppError(ErrorCode.INVALID_STATE, status_code=409)
            CheckpointService(db).assert_resume_compatible(job)
            pre_translation_stages = {
                "split_sections",
                "extract_terms",
                "interrupt_for_term_review",
            }
            if job.current_stage == "parse_document":
                job.status = JobStatus.UPLOADED.value
            elif job.current_stage in pre_translation_stages:
                job.status = JobStatus.PARSED.value
            else:
                job.status = JobStatus.TRANSLATING.value
            job.current_stage = "resume"
            job.error_code = None
            job.error_message = None
            job.retry_count += 1
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
        self.enqueue(job_id)

    def resume_review(self, job_id: str, payload: dict[str, Any] | None = None) -> None:
        self.enqueue(job_id, payload or {"confirmed": True}, priority=10)

    def shutdown(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=10)

    def _claim_next(self) -> tuple[str, dict[str, Any] | None] | None:
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            item = db.scalar(
                select(JobQueue)
                .where(
                    JobQueue.available_at <= now,
                    or_(
                        JobQueue.status == "QUEUED",
                        JobQueue.lease_expires_at < now,
                    ),
                )
                .order_by(JobQueue.priority.desc(), JobQueue.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if item is None:
                return None
            item.status = "LEASED"
            item.lease_owner = self.worker_id
            item.lease_expires_at = now + timedelta(minutes=30)
            item.updated_at = now
            payload = item.resume_payload
            db.commit()
            return item.job_id, payload

    def _execute(self, job_id: str, resume_payload: dict[str, Any] | None) -> None:
        heartbeat_stop = Event()
        heartbeat = Thread(
            target=self._heartbeat,
            args=(job_id, heartbeat_stop),
            name=f"lease-{job_id}",
            daemon=True,
        )
        heartbeat.start()
        try:
            self.runner.run(job_id, resume_payload)
        except Exception as exc:
            logger.exception("workflow failed for %s", job_id)
            with SessionLocal() as db:
                job = db.get(TranslationJob, job_id)
                if job and job.status != JobStatus.CANCELLED.value:
                    job.status = JobStatus.FAILED.value
                    job.error_code = (
                        str(int(exc.code))
                        if isinstance(exc, AppError)
                        else str(int(ErrorCode.INTERNAL_ERROR))
                    )
                    job.error_message = str(exc)
                    job.updated_at = datetime.now(timezone.utc)
                    db.commit()
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=2)
            with SessionLocal() as db:
                item = db.get(JobQueue, job_id)
                if item and item.lease_owner == self.worker_id:
                    db.delete(item)
                    db.commit()

    def _heartbeat(self, job_id: str, stop: Event) -> None:
        while not stop.wait(60):
            with SessionLocal() as db:
                item = db.get(JobQueue, job_id)
                if item is None or item.lease_owner != self.worker_id:
                    return
                now = datetime.now(timezone.utc)
                item.lease_expires_at = now + timedelta(minutes=30)
                item.updated_at = now
                db.commit()


_worker: WorkerService | None = None


def get_worker() -> WorkerService:
    global _worker
    if _worker is None:
        _worker = WorkerService()
    return _worker
