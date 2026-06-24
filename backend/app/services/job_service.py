from datetime import datetime, timezone
from pathlib import Path
from shutil import copyfileobj
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
    JobStatus.WAITING_RISK_REVIEW.value,
    JobStatus.WAITING_CHAPTER_REVIEW.value,
    JobStatus.TRANSLATING.value,
}


class JobService:
    def __init__(self, db: Session, paths: StoragePaths) -> None:
        self.db = db
        self.paths = paths
        self.settings = get_settings()

    async def create_job(
        self,
        upload: UploadFile,
        mode: str,
        ocr_mode: str = "auto",
        require_high_risk_review: bool = False,
        require_chapter_review: bool = False,
    ) -> TranslationJob:
        original_filename, extension = self._validate_request(
            upload.filename, mode, ocr_mode
        )
        job_id, upload_dir, stored_path = self._allocate_upload(extension)
        try:
            await self._save_upload(upload, stored_path)
            return self._persist_job(
                job_id,
                original_filename,
                stored_path,
                mode,
                ocr_mode,
                require_high_risk_review,
                require_chapter_review,
            )
        except Exception:
            self.db.rollback()
            self._cleanup_upload(upload_dir, stored_path)
            raise
        finally:
            await upload.close()

    def create_job_from_path(
        self,
        source: Path,
        original_filename: str,
        mode: str = "paper",
        ocr_mode: str = "auto",
        require_high_risk_review: bool = False,
        require_chapter_review: bool = False,
    ) -> TranslationJob:
        """Create a job from a Gradio temporary file without coupling UI to FastAPI."""
        original_filename, extension = self._validate_request(
            original_filename, mode, ocr_mode
        )
        job_id, upload_dir, stored_path = self._allocate_upload(extension)
        try:
            self._copy_upload(source, stored_path)
            return self._persist_job(
                job_id,
                original_filename,
                stored_path,
                mode,
                ocr_mode,
                require_high_risk_review,
                require_chapter_review,
            )
        except Exception:
            self.db.rollback()
            self._cleanup_upload(upload_dir, stored_path)
            raise

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

        now = datetime.now(timezone.utc)
        job.status = JobStatus.CANCELLED.value
        job.current_stage = "cancelled"
        job.cancelled_at = now
        job.updated_at = now
        self.db.commit()
        self.db.refresh(job)
        return job

    def _has_active_job(self) -> bool:
        statement = select(TranslationJob.job_id).where(
            TranslationJob.status.in_(ACTIVE_STATUSES)
        )
        return self.db.scalar(statement.limit(1)) is not None

    def _validate_request(
        self, filename: str | None, mode: str, ocr_mode: str
    ) -> tuple[str, str]:
        original_filename = Path(filename or "").name
        extension = Path(original_filename).suffix.lower()
        if not original_filename or extension not in SUPPORTED_EXTENSIONS:
            raise AppError(ErrorCode.UNSUPPORTED_FILE_TYPE, status_code=400)
        if mode not in {"paper", "novel"}:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "mode 仅支持 paper 或 novel",
                status_code=422,
            )
        if ocr_mode not in {"auto", "off", "force"}:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "ocrMode 必须是 auto、off 或 force",
                status_code=422,
            )
        if self._has_active_job():
            raise AppError(ErrorCode.SINGLE_JOB_BUSY, status_code=409)
        return original_filename, extension

    def _allocate_upload(self, extension: str) -> tuple[str, Path, Path]:
        job_id = self._new_job_id()
        upload_dir = self.paths.upload_dir(job_id)
        upload_dir.mkdir(parents=True, exist_ok=False)
        return job_id, upload_dir, upload_dir / f"original{extension}"

    def _persist_job(
        self,
        job_id: str,
        original_filename: str,
        stored_path: Path,
        mode: str,
        ocr_mode: str,
        require_high_risk_review: bool,
        require_chapter_review: bool,
    ) -> TranslationJob:
        now = datetime.now(timezone.utc)
        job = TranslationJob(
            job_id=job_id,
            original_filename=original_filename,
            original_file_path=str(stored_path),
            parsed_markdown_path=None,
            document_ir_path=None,
            document_ir_version=None,
            output_manifest_path=None,
            mode=mode,
            ocr_mode=ocr_mode,
            workflow_version=self.settings.workflow_version,
            prompt_version=self.settings.prompt_version,
            max_token_budget=self.settings.job_max_token_budget,
            max_cost_usd=self.settings.job_max_cost_usd,
            require_high_risk_review=require_high_risk_review,
            require_chapter_review=require_chapter_review,
            status=JobStatus.UPLOADED.value,
            current_stage="uploaded",
            created_at=now,
            updated_at=now,
        )
        self.db.add(job)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(ErrorCode.SINGLE_JOB_BUSY, status_code=409) from exc
        self.db.refresh(job)
        return job

    async def _save_upload(self, upload: UploadFile, destination: Path) -> None:
        total_bytes = 0
        with destination.open("xb") as target:
            while chunk := await upload.read(self.settings.upload_read_size):
                total_bytes += len(chunk)
                if total_bytes > self.settings.max_upload_bytes:
                    raise AppError(ErrorCode.FILE_TOO_LARGE, status_code=413)
                target.write(chunk)

    def _copy_upload(self, source: Path, destination: Path) -> None:
        if source.stat().st_size > self.settings.max_upload_bytes:
            raise AppError(ErrorCode.FILE_TOO_LARGE, status_code=413)
        with source.open("rb") as source_file, destination.open("xb") as target:
            copyfileobj(source_file, target, self.settings.upload_read_size)

    @staticmethod
    def _cleanup_upload(upload_dir: Path, stored_path: Path) -> None:
        stored_path.unlink(missing_ok=True)
        try:
            upload_dir.rmdir()
        except OSError:
            pass

    @staticmethod
    def _new_job_id() -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"job_{timestamp}_{uuid4().hex[:8]}"
