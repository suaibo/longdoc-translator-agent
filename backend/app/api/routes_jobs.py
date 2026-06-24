from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.response import success
from app.db.session import get_db
from app.models.translation_job import TranslationJob
from app.schemas.job import JobCreatedResponse, JobResponse, JobStatusResponse
from app.services.job_service import JobService
from app.storage.paths import StoragePaths, get_storage_paths

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def get_job_service(
    db: Annotated[Session, Depends(get_db)],
    paths: Annotated[StoragePaths, Depends(get_storage_paths)],
) -> JobService:
    return JobService(db, paths)


@router.post("")
async def create_job(
    service: Annotated[JobService, Depends(get_job_service)],
    file: Annotated[UploadFile, File()],
    mode: Annotated[str, Form()] = "paper",
) -> dict[str, Any]:
    job = await service.create_job(file, mode)
    data = JobCreatedResponse(job_id=job.job_id).model_dump(by_alias=True)
    return success(data)


@router.get("")
def list_jobs(service: Annotated[JobService, Depends(get_job_service)]) -> dict[str, Any]:
    return success([serialize_job(job) for job in service.list_jobs()])


@router.get("/{job_id}")
def get_job(
    job_id: str, service: Annotated[JobService, Depends(get_job_service)]
) -> dict[str, Any]:
    return success(serialize_job(service.get_job(job_id)))


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: str, service: Annotated[JobService, Depends(get_job_service)]
) -> dict[str, Any]:
    job = service.cancel_job(job_id)
    data = JobStatusResponse(job_id=job.job_id, status=job.status).model_dump(by_alias=True)
    return success(data)


def serialize_job(job: TranslationJob) -> dict[str, Any]:
    return JobResponse.model_validate(
        {
            "job_id": job.job_id,
            "original_filename": job.original_filename,
            "mode": job.mode,
            "status": job.status,
            "current_stage": job.current_stage,
            "total_chunks": job.total_chunks,
            "completed_chunks": job.completed_chunks,
            "progress_percent": job.progress_percent,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }
    ).model_dump(by_alias=True, mode="json")
