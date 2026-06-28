from datetime import datetime, timedelta, timezone
from pathlib import Path
from shutil import copyfileobj
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.models.enums import JobStatus
from app.models.job_queue import JobQueue
from app.models.translation_job import TranslationJob
from app.services.model_catalog_service import ModelCatalogService
from app.storage.object_store import ObjectStorageService
from app.storage.paths import StoragePaths

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt"}
SUPPORTED_LANGUAGES = {"zh", "en", "ja", "ko", "fr", "de", "es", "pt", "ru", "ar"}
ACTIVE_STATUSES = {
    JobStatus.UPLOADED.value,
    JobStatus.PARSED.value,
    JobStatus.WAITING_TERM_REVIEW.value,
    JobStatus.WAITING_STYLE_REVIEW.value,
    JobStatus.WAITING_RISK_REVIEW.value,
    JobStatus.WAITING_CHAPTER_REVIEW.value,
    JobStatus.TRANSLATING.value,
}


class JobService:
    def __init__(
        self,
        db: Session,
        paths: StoragePaths,
        object_storage: ObjectStorageService | None = None,
    ) -> None:
        self.db = db
        self.paths = paths
        self.settings = get_settings()
        self.object_storage = object_storage or ObjectStorageService(paths)

    async def create_job(
        self,
        upload: UploadFile,
        mode: str,
        ocr_mode: str = "auto",
        require_high_risk_review: bool = False,
        require_chapter_review: bool = False,
        target_language: str = "zh",
        selected_model: str | None = None,
        user_id: str = "usr_legacy",
    ) -> TranslationJob:
        original_filename, extension = self._validate_request(
            upload.filename, mode, ocr_mode, target_language
        )
        selected_model = ModelCatalogService().validate(selected_model)
        job_id, upload_dir, stored_path = self._allocate_upload(extension)
        try:
            await self._save_upload(upload, stored_path)
            storage_key = self.object_storage.source_key(user_id, job_id, extension)
            self.object_storage.upload_file(stored_path, storage_key)
            return self._persist_job(
                job_id,
                user_id,
                original_filename,
                stored_path,
                storage_key,
                mode,
                ocr_mode,
                target_language,
                require_high_risk_review,
                require_chapter_review,
                selected_model,
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
        target_language: str = "zh",
        selected_model: str | None = None,
        user_id: str = "usr_legacy",
    ) -> TranslationJob:
        """Create a job from a Gradio temporary file without internal HTTP calls."""
        original_filename, extension = self._validate_request(
            original_filename, mode, ocr_mode, target_language
        )
        selected_model = ModelCatalogService().validate(selected_model)
        job_id, upload_dir, stored_path = self._allocate_upload(extension)
        try:
            self._copy_upload(source, stored_path)
            storage_key = self.object_storage.source_key(user_id, job_id, extension)
            self.object_storage.upload_file(stored_path, storage_key)
            return self._persist_job(
                job_id,
                user_id,
                original_filename,
                stored_path,
                storage_key,
                mode,
                ocr_mode,
                target_language,
                require_high_risk_review,
                require_chapter_review,
                selected_model,
            )
        except Exception:
            self.db.rollback()
            self._cleanup_upload(upload_dir, stored_path)
            raise

    def list_jobs(self, user_id: str | None = None) -> list[TranslationJob]:
        statement = select(TranslationJob)
        if user_id is not None:
            statement = statement.where(TranslationJob.user_id == user_id)
        return list(
            self.db.scalars(statement.order_by(TranslationJob.created_at.desc()))
        )

    def queue_position(self, job_id: str) -> int | None:
        item = self.db.get(JobQueue, job_id)
        if item is None or item.status != "QUEUED":
            return None
        ahead = self.db.scalar(
            select(func.count())
            .select_from(JobQueue)
            .where(
                JobQueue.status == "QUEUED",
                JobQueue.available_at <= item.available_at,
                JobQueue.created_at < item.created_at,
            )
        )
        return int(ahead or 0) + 1

    def get_job(self, job_id: str, user_id: str | None = None) -> TranslationJob:
        job = self.db.get(TranslationJob, job_id)
        if job is None or (user_id is not None and job.user_id != user_id):
            raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
        return job

    def cancel_job(self, job_id: str, user_id: str | None = None) -> TranslationJob:
        job = self.get_job(job_id, user_id)
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

    def _validate_request(
        self, filename: str | None, mode: str, ocr_mode: str, target_language: str
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
        if target_language not in SUPPORTED_LANGUAGES:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "不支持该目标语言",
                status_code=422,
            )
        return original_filename, extension

    def _allocate_upload(self, extension: str) -> tuple[str, Path, Path]:
        job_id = self._new_job_id()
        upload_dir = self.paths.upload_dir(job_id)
        upload_dir.mkdir(parents=True, exist_ok=False)
        return job_id, upload_dir, upload_dir / f"original{extension}"

    def _persist_job(
        self,
        job_id: str,
        user_id: str,
        original_filename: str,
        stored_path: Path,
        storage_key: str,
        mode: str,
        ocr_mode: str,
        target_language: str,
        require_high_risk_review: bool,
        require_chapter_review: bool,
        selected_model: str,
    ) -> TranslationJob:
        now = datetime.now(timezone.utc)
        job = TranslationJob(
            job_id=job_id,
            user_id=user_id,
            original_filename=original_filename,
            original_file_path=str(stored_path),
            parsed_markdown_path=None,
            document_ir_path=None,
            document_ir_version=None,
            output_manifest_path=None,
            source_storage_key=storage_key,
            output_storage_prefix=self.object_storage.output_prefix(user_id, job_id),
            mode=mode,
            ocr_mode=ocr_mode,
            source_language=None,
            target_language=target_language,
            selected_model=selected_model,
            style_preset=None,
            style_prompt=None,
            style_confirmed_at=None,
            workflow_version=self.settings.workflow_version,
            prompt_version=self.settings.prompt_version,
            max_token_budget=self.settings.job_max_token_budget,
            max_cost_usd=self.settings.job_max_cost_usd,
            require_high_risk_review=require_high_risk_review,
            require_chapter_review=require_chapter_review,
            status=JobStatus.UPLOADED.value,
            current_stage="uploaded",
            eta_seconds=None,
            has_unresolved_risks=False,
            outputs_stale=False,
            retention_expires_at=now
            + timedelta(days=self.settings.file_retention_days),
            created_at=now,
            updated_at=now,
        )
        self.db.add(job)
        self.db.commit()
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
