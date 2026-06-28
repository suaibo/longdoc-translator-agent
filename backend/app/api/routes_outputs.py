from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.core.errors import AppError, ErrorCode
from app.core.response import success
from app.db.session import get_db
from app.models.enums import JobStatus
from app.schemas.output import OutputItem
from app.services.event_service import EventService
from app.services.job_service import JobService
from app.services.output_service import OUTPUT_TYPES, OutputService
from app.storage.object_store import ObjectStorageService
from app.storage.paths import StoragePaths, get_storage_paths

router = APIRouter(prefix="/api/jobs/{job_id}", tags=["outputs"])


def get_output_service(
    db: Annotated[Session, Depends(get_db)],
    paths: Annotated[StoragePaths, Depends(get_storage_paths)],
) -> OutputService:
    return OutputService(db, paths)


def _owned_job(service: OutputService, job_id: str, user_id: str):
    return JobService(service.db, service.paths).get_job(job_id, user_id)


@router.get("/outputs")
def list_outputs(
    job_id: str,
    user: CurrentUser,
    service: Annotated[OutputService, Depends(get_output_service)],
) -> dict[str, Any]:
    job = _owned_job(service, job_id, user.user_id)
    items = service.list_outputs(job_id)
    if ObjectStorageService(service.paths).backend == "s3":
        for item in items:
            item["available"] = job.status == JobStatus.COMPLETED.value
    return success(
        [OutputItem.model_validate(item).model_dump(by_alias=True) for item in items]
    )


@router.get("/outputs/{output_type}")
def download_output(
    job_id: str,
    output_type: str,
    user: CurrentUser,
    service: Annotated[OutputService, Depends(get_output_service)],
):
    job = _owned_job(service, job_id, user.user_id)
    if job.status != JobStatus.COMPLETED.value:
        raise AppError(ErrorCode.INVALID_STATE, status_code=409)
    if output_type not in OUTPUT_TYPES:
        raise AppError(ErrorCode.OUTPUT_NOT_FOUND, status_code=404)
    filename, media_type = OUTPUT_TYPES[output_type]
    storage = ObjectStorageService(service.paths)
    if storage.backend == "s3":
        key = f"{storage.output_prefix(user.user_id, job_id)}{filename}"
        url = storage.presigned_download(key, filename)
        if url:
            return RedirectResponse(url=url, status_code=307)
    path = service.get_output(job_id, output_type)
    return FileResponse(path, filename=filename, media_type=media_type)


@router.post("/outputs/regenerate")
def regenerate_outputs(
    job_id: str,
    user: CurrentUser,
    service: Annotated[OutputService, Depends(get_output_service)],
) -> dict[str, Any]:
    job = _owned_job(service, job_id, user.user_id)
    if job.status != JobStatus.COMPLETED.value:
        raise AppError(ErrorCode.INVALID_STATE, status_code=409)
    service.generate_documents(job_id)
    service.generate_report(job_id)
    service.generate_manifest_and_package(job_id)
    ObjectStorageService(service.paths).sync_outputs(job)
    job.outputs_stale = False
    service.db.commit()
    EventService(service.db).record_job_event(
        job_id,
        "OUTPUT",
        "REGENERATED",
        "输出文件已根据当前译文重新生成",
    )
    return success({"jobId": job_id, "outputsStale": False})


@router.get("/source")
def download_source(
    job_id: str,
    user: CurrentUser,
    service: Annotated[OutputService, Depends(get_output_service)],
):
    job = _owned_job(service, job_id, user.user_id)
    storage = ObjectStorageService(service.paths)
    if storage.backend == "s3" and job.source_storage_key:
        url = storage.presigned_download(job.source_storage_key, job.original_filename)
        if url:
            return RedirectResponse(url=url, status_code=307)
    path, filename = service.source_file(job_id)
    return FileResponse(path, filename=filename)
