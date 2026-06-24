from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.response import success
from app.db.session import get_db
from app.schemas.output import OutputItem
from app.services.output_service import OUTPUT_TYPES, OutputService
from app.storage.paths import StoragePaths, get_storage_paths

router = APIRouter(prefix="/api/jobs/{job_id}", tags=["outputs"])


def get_output_service(
    db: Annotated[Session, Depends(get_db)],
    paths: Annotated[StoragePaths, Depends(get_storage_paths)],
) -> OutputService:
    return OutputService(db, paths)


@router.get("/outputs")
def list_outputs(
    job_id: str,
    service: Annotated[OutputService, Depends(get_output_service)],
) -> dict[str, Any]:
    return success(
        [
            OutputItem.model_validate(item).model_dump(by_alias=True)
            for item in service.list_outputs(job_id)
        ]
    )


@router.get("/outputs/{output_type}")
def download_output(
    job_id: str,
    output_type: str,
    service: Annotated[OutputService, Depends(get_output_service)],
) -> FileResponse:
    path = service.get_output(job_id, output_type)
    filename, media_type = OUTPUT_TYPES[output_type]
    return FileResponse(path, filename=filename, media_type=media_type)


@router.get("/source")
def download_source(
    job_id: str,
    service: Annotated[OutputService, Depends(get_output_service)],
) -> FileResponse:
    path, filename = service.source_file(job_id)
    return FileResponse(path, filename=filename)
