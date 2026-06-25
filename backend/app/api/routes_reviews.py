from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.api.routes_jobs import get_background_worker
from app.core.response import success
from app.db.session import get_db
from app.schemas.review import ApproveReviewRequest, ReviewResponse
from app.services.job_service import JobService
from app.services.review_service import ReviewService
from app.services.worker_service import WorkerService
from app.storage.paths import get_storage_paths

router = APIRouter(prefix="/api/jobs/{job_id}/reviews", tags=["reviews"])


def _serialize(review) -> dict[str, Any]:
    return ReviewResponse.model_validate(
        {
            "review_id": review.review_id,
            "review_type": review.review_type,
            "subject_id": review.subject_id,
            "status": review.status,
            "payload": review.payload_json,
            "resolution_note": review.resolution_note,
            "created_at": review.created_at,
            "resolved_at": review.resolved_at,
        }
    ).model_dump(by_alias=True, mode="json")


@router.get("")
def list_reviews(
    job_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
    return success(
        [_serialize(item) for item in ReviewService(db).list_reviews(job_id)]
    )


@router.post("/{review_id}/approve")
def approve_review(
    job_id: str,
    review_id: str,
    request: ApproveReviewRequest,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    worker: Annotated[WorkerService, Depends(get_background_worker)],
) -> dict[str, Any]:
    JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
    review = ReviewService(db).approve(job_id, review_id, request.note)
    worker.resume_review(job_id, {"approved": True, "reviewId": review_id})
    return success(_serialize(review))
