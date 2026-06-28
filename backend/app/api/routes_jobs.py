from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.models.translation_job import TranslationJob
from app.schemas.job import JobCreatedResponse, JobResponse, JobStatusResponse
from app.services.job_service import JobService
from app.services.worker_service import WorkerService, get_worker
from app.storage.paths import StoragePaths, get_storage_paths

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def get_background_worker() -> WorkerService:
    return get_worker()


def get_job_service(
    db: Annotated[Session, Depends(get_db)],
    paths: Annotated[StoragePaths, Depends(get_storage_paths)],
) -> JobService:
    return JobService(db, paths)


@router.post("")
async def create_job(
    user: CurrentUser,
    service: Annotated[JobService, Depends(get_job_service)],
    worker: Annotated[WorkerService, Depends(get_background_worker)],
    file: Annotated[UploadFile, File()],
    mode: Annotated[str, Form()] = "paper",
    ocr_mode: Annotated[str, Form(alias="ocrMode")] = "auto",
    target_language: Annotated[str, Form(alias="targetLanguage")] = "zh",
    selected_model: Annotated[str | None, Form(alias="selectedModel")] = None,
    require_high_risk_review: Annotated[
        bool, Form(alias="requireHighRiskReview")
    ] = False,
    require_chapter_review: Annotated[bool, Form(alias="requireChapterReview")] = False,
) -> dict[str, Any]:
    job = await service.create_job(
        file,
        mode,
        ocr_mode,
        require_high_risk_review,
        require_chapter_review,
        target_language=target_language,
        selected_model=selected_model,
        user_id=user.user_id,
    )
    worker.enqueue(job.job_id)
    return success(JobCreatedResponse(job_id=job.job_id).model_dump(by_alias=True))


@router.get("")
def list_jobs(
    user: CurrentUser,
    service: Annotated[JobService, Depends(get_job_service)],
) -> dict[str, Any]:
    return success(
        [
            serialize_job(job, service.queue_position(job.job_id))
            for job in service.list_jobs(user.user_id)
        ]
    )


@router.get("/{job_id}")
def get_job(
    job_id: str,
    user: CurrentUser,
    service: Annotated[JobService, Depends(get_job_service)],
) -> dict[str, Any]:
    job = service.get_job(job_id, user.user_id)
    return success(serialize_job(job, service.queue_position(job_id)))


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: str,
    user: CurrentUser,
    service: Annotated[JobService, Depends(get_job_service)],
) -> dict[str, Any]:
    job = service.cancel_job(job_id, user.user_id)
    return success(
        JobStatusResponse(job_id=job.job_id, status=job.status).model_dump(
            by_alias=True
        )
    )


@router.post("/{job_id}/resume")
def resume_job(
    job_id: str,
    user: CurrentUser,
    service: Annotated[JobService, Depends(get_job_service)],
    worker: Annotated[WorkerService, Depends(get_background_worker)],
) -> dict[str, Any]:
    service.get_job(job_id, user.user_id)
    worker.resume(job_id)
    service.db.expire_all()
    job = service.get_job(job_id, user.user_id)
    return success(
        JobStatusResponse(job_id=job.job_id, status=job.status).model_dump(
            by_alias=True
        )
    )


def serialize_job(
    job: TranslationJob, queue_position: int | None = None
) -> dict[str, Any]:
    return JobResponse.model_validate(
        {
            "job_id": job.job_id,
            "original_filename": job.original_filename,
            "mode": job.mode,
            "source_language": job.source_language,
            "target_language": job.target_language,
            "selected_model": job.selected_model,
            "style_preset": job.style_preset,
            "style_prompt": job.style_prompt,
            "style_confirmed_at": job.style_confirmed_at,
            "status": job.status,
            "current_stage": job.current_stage,
            "total_chunks": job.total_chunks,
            "completed_chunks": job.completed_chunks,
            "progress_percent": job.progress_percent,
            "eta_seconds": job.eta_seconds,
            "queue_position": queue_position,
            "has_unresolved_risks": job.has_unresolved_risks,
            "outputs_stale": job.outputs_stale,
            "require_high_risk_review": job.require_high_risk_review,
            "require_chapter_review": job.require_chapter_review,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }
    ).model_dump(by_alias=True, mode="json")
