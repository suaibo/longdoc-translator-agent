from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.models.chunk_translation_version import ChunkTranslationVersion
from app.models.document_chunk import DocumentChunk
from app.models.enums import ChunkStatus, JobStatus
from app.models.translation_job import TranslationJob

EDITABLE_JOB_STATUSES = {
    JobStatus.COMPLETED.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELLED.value,
}


class ChunkEditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record_version(
        self,
        job: TranslationJob,
        chunk: DocumentChunk,
        source_type: str,
        translated_text: str,
        *,
        edit_note: str | None = None,
        created_by_user_id: str | None = None,
        model: str | None = None,
    ) -> ChunkTranslationVersion:
        version_no = self._next_version_no(chunk.chunk_id)
        version = ChunkTranslationVersion(
            version_id=f"ver_{uuid4().hex}",
            job_id=job.job_id,
            chunk_id=chunk.chunk_id,
            version_no=version_no,
            source_type=source_type,
            translated_text=translated_text,
            edit_note=edit_note,
            created_by_user_id=created_by_user_id,
            model=model,
            prompt_version=job.prompt_version,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(version)
        return version

    def update_translation(
        self,
        job_id: str,
        chunk_id: str,
        user_id: str,
        translated_text: str,
        edit_note: str | None = None,
    ) -> DocumentChunk:
        job, chunk = self._editable_chunk(job_id, chunk_id)
        cleaned = translated_text.strip()
        if not cleaned:
            raise AppError(
                ErrorCode.VALIDATION_ERROR, "译文不能为空", status_code=422
            )
        chunk.translated_text = cleaned
        chunk.revision_count += 1
        chunk.updated_at = datetime.now(timezone.utc)
        job.outputs_stale = True
        job.updated_at = chunk.updated_at
        self.record_version(
            job,
            chunk,
            "USER_EDIT",
            cleaned,
            edit_note=edit_note,
            created_by_user_id=user_id,
        )
        self.db.commit()
        self.db.refresh(chunk)
        return chunk

    def restore_version(
        self,
        job_id: str,
        chunk_id: str,
        version_id: str,
        user_id: str,
    ) -> DocumentChunk:
        job, chunk = self._editable_chunk(job_id, chunk_id)
        version = self.db.get(ChunkTranslationVersion, version_id)
        if (
            version is None
            or version.job_id != job_id
            or version.chunk_id != chunk_id
        ):
            raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
        chunk.translated_text = version.translated_text
        chunk.revision_count += 1
        chunk.updated_at = datetime.now(timezone.utc)
        job.outputs_stale = True
        job.updated_at = chunk.updated_at
        self.record_version(
            job,
            chunk,
            "RESTORE",
            version.translated_text,
            edit_note=f"restore {version.version_no}",
            created_by_user_id=user_id,
            model=version.model,
        )
        self.db.commit()
        self.db.refresh(chunk)
        return chunk

    def list_versions(
        self, job_id: str, chunk_id: str
    ) -> list[ChunkTranslationVersion]:
        return list(
            self.db.scalars(
                select(ChunkTranslationVersion)
                .where(
                    ChunkTranslationVersion.job_id == job_id,
                    ChunkTranslationVersion.chunk_id == chunk_id,
                )
                .order_by(ChunkTranslationVersion.version_no.desc())
            )
        )

    def _editable_chunk(
        self, job_id: str, chunk_id: str
    ) -> tuple[TranslationJob, DocumentChunk]:
        job = self.db.get(TranslationJob, job_id)
        chunk = self.db.get(DocumentChunk, chunk_id)
        if job is None or chunk is None or chunk.job_id != job_id:
            raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
        if job.status not in EDITABLE_JOB_STATUSES:
            raise AppError(
                ErrorCode.INVALID_STATE,
                "任务运行中不能编辑正式译文，请等待任务结束后再编辑",
                status_code=409,
            )
        if chunk.status != ChunkStatus.COMPLETED.value or not chunk.translated_text:
            raise AppError(
                ErrorCode.INVALID_STATE,
                "只能编辑已经完成翻译的 chunk",
                status_code=409,
            )
        return job, chunk

    def _next_version_no(self, chunk_id: str) -> int:
        current = self.db.scalar(
            select(func.max(ChunkTranslationVersion.version_no)).where(
                ChunkTranslationVersion.chunk_id == chunk_id
            )
        )
        return int(current or 0) + 1
