from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.schemas.job import to_camel
from app.services.event_service import EventService
from app.services.job_service import JobService
from app.services.pretranslation_service import PretranslationService
from app.services.worker_service import WorkerService, get_worker
from app.storage.paths import get_storage_paths

router = APIRouter(prefix="/api/jobs/{job_id}/pretranslation", tags=["pretranslation"])


class StyleRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    style_prompt: str | None = None
    style_preset: str | None = None


class PretranslationResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    preview_id: str
    attempt_no: int
    sample_chunk_ids: list[str]
    source_text: str
    translated_text: str
    style_prompt: str | None
    selected_model: str | None
    status: str
    created_at: datetime
    accepted_at: datetime | None


def get_background_worker() -> WorkerService:
    return get_worker()


@router.get("")
def get_latest_pretranslation(
    job_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
    preview = PretranslationService(db).latest(job_id)
    return success(_serialize(preview) if preview else None)


@router.post("/retry")
def retry_pretranslation(
    job_id: str,
    request: StyleRequest,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
    preview = PretranslationService(db).generate(job_id, request.style_prompt)
    EventService(db).record_job_event(
        job_id,
        "STYLE",
        "PREVIEWED",
        "预翻译样例已生成",
        {"previewId": preview.preview_id, "attemptNo": preview.attempt_no},
    )
    return success(_serialize(preview))


@router.post("/confirm")
def confirm_style(
    job_id: str,
    request: StyleRequest,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    worker: Annotated[WorkerService, Depends(get_background_worker)],
) -> dict[str, Any]:
    JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
    job = PretranslationService(db).confirm_style(
        job_id, request.style_prompt, request.style_preset
    )
    EventService(db).record_job_event(
        job_id,
        "STYLE",
        "CONFIRMED",
        "翻译风格已确认，正式翻译继续",
        {"stylePreset": job.style_preset},
    )
    worker.resume_review(job_id, {"styleConfirmed": True})
    return success({"jobId": job.job_id, "status": job.status})


def _serialize(preview) -> dict[str, Any]:
    return PretranslationResponse.model_validate(
        {
            "preview_id": preview.preview_id,
            "attempt_no": preview.attempt_no,
            "sample_chunk_ids": preview.sample_chunk_ids,
            "source_text": preview.source_text,
            "translated_text": preview.translated_text,
            "style_prompt": preview.style_prompt,
            "selected_model": preview.selected_model,
            "status": preview.status,
            "created_at": preview.created_at,
            "accepted_at": preview.accepted_at,
        }
    ).model_dump(by_alias=True, mode="json")
