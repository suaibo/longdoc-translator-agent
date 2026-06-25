import shutil
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import JobStatus
from app.models.translation_job import TranslationJob
from app.storage.object_store import ObjectStorageService
from app.storage.paths import StoragePaths


class RetentionService:
    """Deletes expired file payloads while retaining task audit metadata."""

    TERMINAL = {
        JobStatus.COMPLETED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELLED.value,
    }

    def __init__(self, db: Session, paths: StoragePaths) -> None:
        self.db = db
        self.paths = paths
        self.storage = ObjectStorageService(paths)

    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        jobs = list(
            self.db.scalars(
                select(TranslationJob).where(
                    TranslationJob.retention_expires_at.is_not(None),
                    TranslationJob.retention_expires_at <= now,
                    TranslationJob.status.in_(self.TERMINAL),
                )
            )
        )
        for job in jobs:
            self.storage.delete_prefix(f"{job.user_id}/{job.job_id}")
            for directory in (
                self.paths.upload_dir(job.job_id),
                self.paths.parsed_dir(job.job_id),
                self.paths.output_dir(job.job_id),
            ):
                if directory.exists():
                    shutil.rmtree(directory)
            job.source_storage_key = None
            job.output_storage_prefix = None
            job.output_manifest_path = None
            job.retention_expires_at = None
        self.db.commit()
        return len(jobs)
