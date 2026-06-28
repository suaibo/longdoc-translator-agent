from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document_chunk import DocumentChunk
from app.models.translation_job import TranslationJob
from app.models.user_account import UserAccount
from app.schemas.llm import LLMResult, LLMUsage
from app.services.chunk_edit_service import ChunkEditService
from app.services.event_service import EventService
from app.services.model_catalog_service import ModelCatalogService
from app.services.pretranslation_service import PretranslationService
from app.services.stream_token_service import StreamTokenService


class PreviewLLM:
    def __init__(self) -> None:
        self.calls = []

    def translate_chunk(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return LLMResult(
            content="样例译文",
            model="deepseek-preview",
            usage=LLMUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        )


def add_job(
    db: Session,
    tmp_path: Path,
    *,
    job_id: str = "job_style",
    status: str = "WAITING_STYLE_REVIEW",
    user_id: str = "usr_legacy",
) -> TranslationJob:
    now = datetime.now(timezone.utc)
    source = tmp_path / f"{job_id}.md"
    source.write_text("# Paper\n\nBody", encoding="utf-8")
    job = TranslationJob(
        job_id=job_id,
        user_id=user_id,
        original_filename=source.name,
        original_file_path=str(source),
        parsed_markdown_path=None,
        document_ir_path=None,
        document_ir_version=None,
        output_manifest_path=None,
        source_storage_key=None,
        output_storage_prefix=None,
        mode="paper",
        ocr_mode="auto",
        source_language="en",
        target_language="zh",
        selected_model="deepseek-preview",
        style_preset=None,
        style_prompt=None,
        workflow_version="1",
        prompt_version="1",
        status=status,
        current_stage="test",
        eta_seconds=None,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    return job


def add_chunk(
    db: Session,
    job_id: str,
    *,
    chunk_id: str = "chunk_style",
    status: str = "PENDING",
    translated_text: str | None = None,
) -> DocumentChunk:
    now = datetime.now(timezone.utc)
    chunk = DocumentChunk(
        chunk_id=chunk_id,
        job_id=job_id,
        chunk_index=0,
        section_title="Intro",
        chunk_type="TEXT",
        source_text="This is a checkpoint paragraph.",
        translated_text=translated_text,
        status=status,
        has_risk=False,
        created_at=now,
        updated_at=now,
    )
    db.add(chunk)
    db.commit()
    return chunk


def test_model_catalog_reads_server_allowlist(monkeypatch) -> None:
    monkeypatch.setenv(
        "LLM_MODEL_OPTIONS_JSON",
        '[{"id":"deepseek-chat","name":"DeepSeek Chat","provider":"deepseek"}]',
    )
    get_settings.cache_clear()
    try:
        catalog = ModelCatalogService()
        assert catalog.default_model() == "deepseek-chat"
        assert catalog.validate("deepseek-chat") == "deepseek-chat"
    finally:
        get_settings.cache_clear()


def test_pretranslation_uses_style_prompt_and_selected_model(
    db_session: Session, tmp_path: Path
) -> None:
    job = add_job(db_session, tmp_path)
    add_chunk(db_session, job.job_id)
    llm = PreviewLLM()

    preview = PretranslationService(db_session, llm=llm).generate(
        job.job_id, "更正式，少口语化"
    )

    assert preview.translated_text == "样例译文"
    assert preview.style_prompt == "更正式，少口语化"
    assert preview.selected_model == "deepseek-preview"
    assert llm.calls[0][0][-1] == "更正式，少口语化"


def test_chunk_edit_creates_version_and_marks_outputs_stale(
    db_session: Session, tmp_path: Path
) -> None:
    job = add_job(db_session, tmp_path, job_id="job_edit", status="COMPLETED")
    chunk = add_chunk(
        db_session,
        job.job_id,
        chunk_id="chunk_edit",
        status="COMPLETED",
        translated_text="旧译文",
    )

    updated = ChunkEditService(db_session).update_translation(
        job.job_id, chunk.chunk_id, "usr_legacy", "新译文", "polish"
    )

    db_session.refresh(job)
    versions = ChunkEditService(db_session).list_versions(job.job_id, chunk.chunk_id)
    assert updated.translated_text == "新译文"
    assert job.outputs_stale is True
    assert versions[0].source_type == "USER_EDIT"
    assert versions[0].translated_text == "新译文"


def test_stream_token_and_event_after_sequence(
    db_session: Session, tmp_path: Path
) -> None:
    job = add_job(db_session, tmp_path, job_id="job_stream", status="COMPLETED")
    token = StreamTokenService().issue("usr_legacy", job.job_id)
    payload = StreamTokenService().verify(token, job.job_id)
    first = EventService(db_session).record(job.job_id, "start", "NODE", "STARTED")
    second = EventService(db_session).record(job.job_id, "done", "NODE", "COMPLETED")

    events = EventService(db_session).list_events(job.job_id, after_seq=first.event_seq)

    assert payload["jobId"] == job.job_id
    assert events == [second]


def test_models_and_stream_token_api(client: TestClient, db_session: Session, tmp_path: Path) -> None:
    owner = db_session.scalar(select(UserAccount).where(UserAccount.username == "testuser"))
    assert owner is not None
    job = add_job(
        db_session,
        tmp_path,
        job_id="job_stream_api",
        status="COMPLETED",
        user_id=owner.user_id,
    )

    models = client.get("/api/models")
    token = client.post(f"/api/jobs/{job.job_id}/events/stream-token")

    assert models.status_code == 200
    assert models.json()["data"][0]["id"]
    assert token.status_code == 200
    assert token.json()["data"]["streamToken"]
