import logging
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from app.agent.runner import WorkflowRunner
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.db.session import SessionLocal
from app.models.enums import JobStatus
from app.models.job_queue import JobQueue
from app.models.translation_job import TranslationJob
from app.services.checkpoint_service import CheckpointService
from app.services.retention_service import RetentionService
from app.storage.object_store import ObjectStorageService
from app.storage.paths import get_storage_paths

logger = logging.getLogger(__name__)


class WorkerService:
    """PostgreSQL leased worker with bounded cross-job concurrency."""

    def __init__(self, *, poll_seconds: float = 1.0) -> None:
        settings = get_settings()
        self.runner = WorkflowRunner()
        self.worker_id = f"worker_{uuid4().hex}"
        self.poll_seconds = poll_seconds
        self.max_concurrency = settings.worker_max_concurrency
        self.user_max_concurrency = settings.user_max_concurrent_jobs
        self.stop_event = Event()
        self.thread: Thread | None = None
        self.executor = ThreadPoolExecutor(
            max_workers=self.max_concurrency,
            thread_name_prefix="longdoc-job",
        )
        self.futures: set[Future] = set()
        self.last_cleanup_at: datetime | None = None

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
            self._run_retention_if_due()
            self._reap_futures()
            claimed = False
            while len(self.futures) < self.max_concurrency:
                item = self._claim_next()
                if item is None:
                    break
                claimed = True
                job_id, payload = item
                self.futures.add(self.executor.submit(self._execute, job_id, payload))
            if not claimed:
                self.stop_event.wait(self.poll_seconds)
        self._reap_futures()

    def run_once(self) -> bool:
        """Synchronous single-item path used by tests and maintenance commands."""
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
                "pretranslate_sample",
                "interrupt_for_style_review",
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
        self.executor.shutdown(wait=True, cancel_futures=False)

    def _run_retention_if_due(self) -> None:
        now = datetime.now(timezone.utc)
        if self.last_cleanup_at and now - self.last_cleanup_at < timedelta(hours=1):
            return
        try:
            with SessionLocal() as db:
                RetentionService(db, get_storage_paths()).cleanup_expired()
            self.last_cleanup_at = now
        except Exception:
            logger.exception("retention cleanup failed")

    def _reap_futures(self) -> None:
        completed = {future for future in self.futures if future.done()}
        self.futures.difference_update(completed)
        for future in completed:
            try:
                future.result()
            except Exception:
                logger.exception("worker execution future failed")

    def _claim_next(self) -> tuple[str, dict[str, Any] | None] | None:
        now = datetime.now(timezone.utc)
        queue_alias = aliased(JobQueue)
        job_alias = aliased(TranslationJob)
        with SessionLocal() as db:
            active_for_user = (
                select(func.count())
                .select_from(queue_alias)
                .join(job_alias, job_alias.job_id == queue_alias.job_id)
                .where(
                    queue_alias.status == "LEASED",
                    queue_alias.lease_expires_at >= now,
                    job_alias.user_id == TranslationJob.user_id,
                )
                .correlate(TranslationJob)
                .scalar_subquery()
            )
            item = db.scalar(
                select(JobQueue)
                .join(TranslationJob, TranslationJob.job_id == JobQueue.job_id)
                .where(
                    JobQueue.available_at <= now,
                    or_(
                        JobQueue.status == "QUEUED",
                        JobQueue.lease_expires_at < now,
                    ),
                    active_for_user < self.user_max_concurrency,
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
            with SessionLocal() as db:
                job = db.get(TranslationJob, job_id)
                if job is not None:
                    ObjectStorageService().materialize_job(job)
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
