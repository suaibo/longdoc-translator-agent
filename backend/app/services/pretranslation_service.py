from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.models.document_chunk import DocumentChunk
from app.models.enums import JobStatus
from app.models.pretranslation_preview import PretranslationPreview
from app.models.translation_job import TranslationJob
from app.services.budget_service import BudgetService
from app.services.llm_service import LLMService
from app.services.metric_service import MetricService
from app.services.term_service import TermService


class PretranslationService:
    SAMPLE_CHUNKS = 2
    SAMPLE_MAX_CHARS = 3500

    def __init__(self, db: Session, llm: LLMService | None = None) -> None:
        self.db = db
        self.llm = llm

    def latest(self, job_id: str) -> PretranslationPreview | None:
        return self.db.scalar(
            select(PretranslationPreview)
            .where(PretranslationPreview.job_id == job_id)
            .order_by(PretranslationPreview.attempt_no.desc())
            .limit(1)
        )

    def generate(
        self,
        job_id: str,
        style_prompt: str | None = None,
    ) -> PretranslationPreview:
        job = self._job(job_id)
        if job.status != JobStatus.WAITING_STYLE_REVIEW.value:
            raise AppError(ErrorCode.INVALID_STATE, status_code=409)
        sample_chunks = self._sample_chunks(job_id)
        if not sample_chunks:
            raise AppError(
                ErrorCode.INVALID_STATE,
                "没有可用于预翻译的正文片段",
                status_code=409,
            )
        source_text = "\n\n".join(chunk.source_text for chunk in sample_chunks)
        source_text = source_text[: self.SAMPLE_MAX_CHARS]
        prompt = self._normalize_style(style_prompt)
        BudgetService(self.db).assert_available(job_id)
        llm = self.llm or self._job_llm(job)
        result = llm.translate_chunk(
            source_text,
            TermService(self.db).confirmed_map(job_id),
            None,
            None,
            None,
            "preview",
            job.target_language,
            prompt,
        )
        MetricService(self.db).record(job_id, result)
        now = datetime.now(timezone.utc)
        attempt_no = self._next_attempt_no(job_id)
        preview = PretranslationPreview(
            preview_id=f"preview_{uuid4().hex}",
            job_id=job_id,
            attempt_no=attempt_no,
            sample_chunk_ids=[chunk.chunk_id for chunk in sample_chunks],
            source_text=source_text,
            translated_text=result.content,
            style_prompt=prompt,
            selected_model=result.model or job.selected_model,
            status="DRAFT",
            metadata_json={"profile": "preview"},
            created_at=now,
            accepted_at=None,
        )
        job.style_prompt = prompt
        job.selected_model = result.model or job.selected_model
        job.current_stage = "interrupt_for_style_review"
        job.updated_at = now
        self.db.add(preview)
        self.db.commit()
        self.db.refresh(preview)
        return preview

    def confirm_style(
        self,
        job_id: str,
        style_prompt: str | None = None,
        style_preset: str | None = None,
    ) -> TranslationJob:
        job = self._job(job_id)
        if job.status != JobStatus.WAITING_STYLE_REVIEW.value:
            raise AppError(ErrorCode.INVALID_STATE, status_code=409)
        now = datetime.now(timezone.utc)
        job.style_prompt = self._normalize_style(style_prompt)
        job.style_preset = style_preset.strip() if style_preset else None
        job.style_confirmed_at = now
        job.status = JobStatus.TRANSLATING.value
        job.current_stage = "translate_chunk"
        job.updated_at = now
        latest = self.latest(job_id)
        if latest is not None:
            latest.status = "ACCEPTED"
            latest.style_prompt = job.style_prompt
            latest.accepted_at = now
        self.db.commit()
        self.db.refresh(job)
        return job

    def _sample_chunks(self, job_id: str) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        for chunk in self.db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.job_id == job_id)
            .order_by(DocumentChunk.chunk_index)
        ):
            if self._can_preview(chunk):
                chunks.append(chunk)
            if len(chunks) >= self.SAMPLE_CHUNKS:
                break
        return chunks

    def _next_attempt_no(self, job_id: str) -> int:
        current = self.db.scalar(
            select(func.max(PretranslationPreview.attempt_no)).where(
                PretranslationPreview.job_id == job_id
            )
        )
        return int(current or 0) + 1

    def _job(self, job_id: str) -> TranslationJob:
        job = self.db.get(TranslationJob, job_id)
        if job is None:
            raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
        return job

    @staticmethod
    def _can_preview(chunk: DocumentChunk) -> bool:
        if chunk.chunk_type != "TEXT":
            return False
        metadata = chunk.structure_metadata or {}
        if metadata.get("translationProtected") is True:
            return False
        return bool(chunk.source_text.strip())

    @staticmethod
    def _normalize_style(style_prompt: str | None) -> str | None:
        cleaned = (style_prompt or "").strip()
        return cleaned or None

    @staticmethod
    def _job_llm(job: TranslationJob) -> LLMService:
        overrides = {}
        if job.selected_model:
            overrides["translation"] = job.selected_model
        return LLMService(task_model_overrides=overrides)
