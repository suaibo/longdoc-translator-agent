from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.routes_jobs import get_background_worker
from app.core.response import success
from app.db.session import get_db
from app.schemas.job import JobStatusResponse
from app.schemas.term import ConfirmTermsRequest, TermResponse
from app.services.term_service import TermService
from app.services.worker_service import WorkerService

router = APIRouter(prefix="/api/jobs/{job_id}/terms", tags=["terms"])


@router.get("")
def list_terms(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
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
    db: Annotated[Session, Depends(get_db)],
    worker: Annotated[WorkerService, Depends(get_background_worker)],
) -> dict[str, Any]:
    TermService(db).confirm(job_id, request.terms)
    worker.resume_review(job_id)
    data = JobStatusResponse(job_id=job_id, status="TRANSLATING").model_dump(
        by_alias=True
    )
    return success(data)
