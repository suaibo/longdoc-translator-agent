from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.translation_job import TranslationJob
from app.schemas.llm import LLMResult, QualityIssue, QualityResult
from app.services.translation_service import TranslationService


class RevisionLLM:
    def __init__(self) -> None:
        self.quality_calls = 0
        self.settings = SimpleNamespace(llm_model="test")

    def check_quality(self, original: str, translated: str):
        self.quality_calls += 1
        issues = (
            [
                QualityIssue(
                    type="OMISSION",
                    message="missing sentence",
                    severity="HIGH",
                )
            ]
            if self.quality_calls == 1
            else []
        )
        return QualityResult(issues=issues), LLMResult(content='{"issues":[]}')

    def revise_translation(self, original, translated, issues, terms):
        return LLMResult(content="修订后的完整译文")


class FailingTranslateLLM:
    def translate_chunk(self, *args, **kwargs):
        raise AssertionError("protected chunks must not call LLM")


def test_high_quality_issue_runs_bounded_revision(
    db_session: Session, monkeypatch
) -> None:
    monkeypatch.setenv("MAX_REVISION_ATTEMPTS", "1")
    from app.core.config import get_settings

    get_settings.cache_clear()
    now = datetime.now(timezone.utc)
    job = TranslationJob(
        job_id="job_revision",
        original_filename="paper.md",
        original_file_path="paper.md",
        mode="paper",
        status="TRANSLATING",
        current_stage="mark_risks",
        created_at=now,
        updated_at=now,
    )
    chunk = DocumentChunk(
        chunk_id="chunk_revision",
        job_id=job.job_id,
        chunk_index=0,
        source_text="Complete source.",
        translated_text="不完整译文",
        status="COMPLETED",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([job, chunk])
    db_session.commit()
    llm = RevisionLLM()
    try:
        risks = TranslationService(db_session, llm=llm).mark_quality_risks(
            job.job_id, chunk
        )
    finally:
        get_settings.cache_clear()

    assert chunk.translated_text == "修订后的完整译文"
    assert chunk.revision_count == 1
    assert llm.quality_calls == 2
    assert risks == []


def test_protected_author_chunk_skips_llm_translation(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    job = TranslationJob(
        job_id="job_protected",
        original_filename="paper.md",
        original_file_path="paper.md",
        mode="paper",
        status="TRANSLATING",
        current_stage="translate_chunk",
        created_at=now,
        updated_at=now,
    )
    source = (
        "| Ashish Vaswani Google Brain avaswani@google.com | "
        "Noam Shazeer Google Brain noam@google.com |\n"
        "| --- | --- |"
    )
    chunk = DocumentChunk(
        chunk_id="chunk_protected",
        job_id=job.job_id,
        chunk_index=0,
        chunk_type="TABLE",
        source_text=source,
        structure_metadata={"translationProtected": True},
        status="PENDING",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([job, chunk])
    db_session.commit()

    translated = TranslationService(db_session, llm=FailingTranslateLLM()).translate(
        job.job_id, chunk, previous_summary=None
    )

    assert translated.translated_text == source
    assert translated.status == "COMPLETED"
