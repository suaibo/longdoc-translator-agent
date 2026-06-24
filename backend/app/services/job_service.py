from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.models.enums import JobStatus
from app.models.translation_job import TranslationJob
from app.storage.paths import StoragePaths

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt"}
ACTIVE_STATUSES = {
    JobStatus.UPLOADED.value,
    JobStatus.PARSED.value,
    JobStatus.WAITING_TERM_REVIEW.value,
    JobStatus.TRANSLATING.value,
}


class JobService:
    def __init__(self, db: Session, paths: StoragePaths) -> None:
        self.db = db
        self.paths = paths
        self.settings = get_settings()

    async def create_job(self, upload: UploadFile, mode: str) -> TranslationJob:
        original_filename = Path(upload.filename or "").name
        extension = Path(original_filename).suffix.lower()
        if not original_filename or extension not in SUPPORTED_EXTENSIONS:
            raise AppError(ErrorCode.UNSUPPORTED_FILE_TYPE, status_code=400)
        if mode != "paper":
            raise AppError(ErrorCode.VALIDATION_ERROR, "mode 目前仅支持 paper", status_code=422)
        if self._has_active_job():
            raise AppError(ErrorCode.SINGLE_JOB_BUSY, status_code=409)

        job_id = self._new_job_id()
        upload_dir = self.paths.upload_dir(job_id)
        upload_dir.mkdir(parents=True, exist_ok=False)
        stored_path = upload_dir / f"original{extension}"

        try:
            await self._save_upload(upload, stored_path)
            now = datetime.now(timezone.utc).isoformat()
            job = TranslationJob(
                job_id=job_id,
                original_filename=original_filename,
                original_file_path=str(stored_path),
                parsed_markdown_path=None,
                mode=mode,
                status=JobStatus.UPLOADED.value,
                current_stage="uploaded",
                created_at=now,
                updated_at=now,
            )
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)
            return job
        except Exception:
            self.db.rollback()
            stored_path.unlink(missing_ok=True)
            try:
                upload_dir.rmdir()
            except OSError:
                pass
            raise
        finally:
            await upload.close()

    def list_jobs(self) -> list[TranslationJob]:
        statement = select(TranslationJob).order_by(TranslationJob.created_at.desc())
        return list(self.db.scalars(statement))

    def get_job(self, job_id: str) -> TranslationJob:
        job = self.db.get(TranslationJob, job_id)
        if job is None:
            raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
        return job

    def cancel_job(self, job_id: str) -> TranslationJob:
        job = self.get_job(job_id)
        if job.status not in ACTIVE_STATUSES:
            raise AppError(ErrorCode.INVALID_STATE, status_code=409)

        now = datetime.now(timezone.utc).isoformat()
        job.status = JobStatus.CANCELLED.value
        job.current_stage = "cancelled"
        job.cancelled_at = now
        job.updated_at = now
        self.db.commit()
        self.db.refresh(job)
        return job

    def _has_active_job(self) -> bool:
        statement = select(TranslationJob.job_id).where(TranslationJob.status.in_(ACTIVE_STATUSES))
        return self.db.scalar(statement.limit(1)) is not None

    async def _save_upload(self, upload: UploadFile, destination: Path) -> None:
        total_bytes = 0
        with destination.open("xb") as target:
            while chunk := await upload.read(self.settings.upload_read_size):
                total_bytes += len(chunk)
                if total_bytes > self.settings.max_upload_bytes:
                    raise AppError(ErrorCode.FILE_TOO_LARGE, status_code=413)
                target.write(chunk)

    @staticmethod
    def _new_job_id() -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"job_{timestamp}_{uuid4().hex[:8]}"
