from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.models.enums import JobStatus
from app.models.term_entry import TermEntry
from app.models.translation_job import TranslationJob
from app.schemas.term import TermConfirmation
from app.services.llm_service import LLMService
from app.services.metric_service import MetricService
from app.services.budget_service import BudgetService


class TermService:
    BATCH_CHARS = 12_000

    def __init__(
        self,
        db: Session,
        llm: LLMService | None = None,
    ) -> None:
        self.db = db
        self.llm = llm

    def extract(self, job_id: str, texts: list[str]) -> list[TermEntry]:
        job = self._get_job(job_id)
        llm = self.llm or LLMService()
        merged: dict[str, tuple[str, str, str | None]] = {}
        content = "\n\n".join(texts)
        for start in range(0, len(content), self.BATCH_CHARS):
            BudgetService(self.db).assert_available(job_id)
            suggestions, result = llm.extract_terms(
                content[start : start + self.BATCH_CHARS]
            )
            MetricService(self.db).record(
                job_id,
                result,
            )
            for suggestion in suggestions:
                key = suggestion.source_term.casefold()
                merged.setdefault(
                    key,
                    (
                        suggestion.source_term,
                        suggestion.suggested_translation,
                        suggestion.note,
                    ),
                )

        now = datetime.now(timezone.utc)
        self.db.execute(delete(TermEntry).where(TermEntry.job_id == job_id))
        entries = [
            TermEntry(
                term_id=self._stable_id(job_id, source_term),
                job_id=job_id,
                source_term=source_term,
                suggested_translation=translation,
                confirmed_translation=None,
                note=note,
                confirmed=False,
                created_at=now,
                updated_at=now,
            )
            for _, (source_term, translation, note) in sorted(merged.items())
        ]
        self.db.add_all(entries)
        job.status = JobStatus.WAITING_TERM_REVIEW.value
        job.current_stage = "interrupt_for_term_review"
        job.updated_at = now
        self.db.commit()
        return entries

    def list_terms(self, job_id: str) -> list[TermEntry]:
        self._get_job(job_id)
        return list(
            self.db.scalars(
                select(TermEntry)
                .where(TermEntry.job_id == job_id)
                .order_by(TermEntry.source_term)
            )
        )

    def confirm(
        self, job_id: str, confirmations: list[TermConfirmation]
    ) -> list[TermEntry]:
        job = self._get_job(job_id)
        if job.status != JobStatus.WAITING_TERM_REVIEW.value:
            raise AppError(ErrorCode.INVALID_STATE, status_code=409)
        entries = self.list_terms(job_id)
        by_id = {entry.term_id: entry for entry in entries}
        if set(by_id) != {confirmation.term_id for confirmation in confirmations}:
            if by_id or confirmations:
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    "提交的术语必须与当前任务术语完整匹配",
                    status_code=422,
                )
        now = datetime.now(timezone.utc)
        for confirmation in confirmations:
            entry = by_id[confirmation.term_id]
            entry.confirmed_translation = confirmation.confirmed_translation
            entry.note = confirmation.note
            entry.confirmed = True
            entry.updated_at = now
        job.status = JobStatus.TRANSLATING.value
        job.current_stage = "translate_chunk"
        job.updated_at = now
        self.db.commit()
        return entries

    def confirmed_map(self, job_id: str) -> dict[str, str]:
        return {
            term.source_term: term.confirmed_translation
            for term in self.list_terms(job_id)
            if term.confirmed and term.confirmed_translation
        }

    def _get_job(self, job_id: str) -> TranslationJob:
        job = self.db.get(TranslationJob, job_id)
        if job is None:
            raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
        return job

    @staticmethod
    def _stable_id(job_id: str, source_term: str) -> str:
        return f"term_{uuid5(NAMESPACE_URL, f'{job_id}:{source_term}').hex}"
