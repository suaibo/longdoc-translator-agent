import logging
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from sqlalchemy import select

from app.agent.runner import WorkflowRunner
from app.core.errors import AppError, ErrorCode
from app.db.session import SessionLocal
from app.models.enums import JobStatus
from app.models.translation_job import TranslationJob
from app.services.checkpoint_service import CheckpointService

logger = logging.getLogger(__name__)


class WorkerService:
    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="longdoc-worker"
        )
        self.runner = WorkflowRunner()
        self.lock = Lock()
        self.futures: dict[str, Future[None]] = {}

    def enqueue(
        self, job_id: str, resume_payload: dict[str, Any] | None = None
    ) -> None:
        with self.lock:
            existing = self.futures.get(job_id)
            if existing and not existing.done():
                return
            future = self.executor.submit(self._execute, job_id, resume_payload)
            self.futures[job_id] = future

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
        for job in jobs:
            self.enqueue(job.job_id)

    def resume(self, job_id: str) -> None:
        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job is None:
                raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
            if job.status == JobStatus.FAILED.value:
                CheckpointService(db).assert_resume_compatible(job)
                job.status = JobStatus.TRANSLATING.value
                job.current_stage = "resume"
                job.error_code = None
                job.error_message = None
                job.retry_count += 1
                job.updated_at = datetime.now(timezone.utc)
                db.commit()
                payload = None
            else:
                raise AppError(ErrorCode.INVALID_STATE, status_code=409)
        self.enqueue(job_id, payload)

    def resume_review(
        self, job_id: str, payload: dict[str, Any] | None = None
    ) -> None:
        self.enqueue(job_id, payload or {"confirmed": True})

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)

    def _execute(
        self, job_id: str, resume_payload: dict[str, Any] | None
    ) -> None:
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


_worker: WorkerService | None = None


def get_worker() -> WorkerService:
    global _worker
    if _worker is None:
        _worker = WorkerService()
    return _worker
