from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.api.routes_jobs import get_background_worker
from app.core.response import success
from app.db.session import get_db
from app.schemas.job import JobStatusResponse
from app.schemas.term import ConfirmTermsRequest, TermResponse
from app.services.job_service import JobService
from app.services.term_service import TermService
from app.services.worker_service import WorkerService
from app.storage.paths import get_storage_paths

router = APIRouter(prefix="/api/jobs/{job_id}/terms", tags=["terms"])


@router.get("")
def list_terms(
    job_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
    terms = TermService(db).list_terms(job_id)
    return success(
        [
            TermResponse.model_validate(
                {
                    "term_id": term.term_id,
                    "source_term": term.source_term,
                    "suggested_translation": term.suggested_translation,
                    "confirmed_translation": term.confirmed_translation,
                    "note": term.note,
                    "confirmed": term.confirmed,
                }
            ).model_dump(by_alias=True)
            for term in terms
        ]
    )


@router.put("")
def confirm_terms(
    job_id: str,
    request: ConfirmTermsRequest,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    worker: Annotated[WorkerService, Depends(get_background_worker)],
) -> dict[str, Any]:
    job_service = JobService(db, get_storage_paths())
    job = job_service.get_job(job_id, user.user_id)
    TermService(db).confirm(job_id, request.terms)
    db.refresh(job)
    worker.resume_review(job_id)
    return success(
        JobStatusResponse(job_id=job_id, status=job.status).model_dump(by_alias=True)
    )
