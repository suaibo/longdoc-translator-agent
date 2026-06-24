from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.models.enums import JobStatus, ReviewStatus, ReviewType
from app.models.review_request import ReviewRequest
from app.models.translation_job import TranslationJob


class ReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create(
        self,
        job_id: str,
        review_type: ReviewType,
        subject_id: str,
        payload: dict,
    ) -> ReviewRequest:
        review = self.db.scalar(
            select(ReviewRequest).where(
                ReviewRequest.job_id == job_id,
                ReviewRequest.review_type == review_type.value,
                ReviewRequest.subject_id == subject_id,
            )
        )
        if review:
            return review
        review = ReviewRequest(
            review_id=f"review_{uuid4().hex}",
            job_id=job_id,
            review_type=review_type.value,
            subject_id=subject_id,
            status=ReviewStatus.PENDING.value,
            payload_json=payload,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(review)
        self.db.commit()
        return review

    def list_reviews(self, job_id: str) -> list[ReviewRequest]:
        if self.db.get(TranslationJob, job_id) is None:
            raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
        return list(
            self.db.scalars(
                select(ReviewRequest)
                .where(ReviewRequest.job_id == job_id)
                .order_by(ReviewRequest.created_at)
            )
        )

    def approve(self, job_id: str, review_id: str, note: str | None) -> ReviewRequest:
        review = self.db.get(ReviewRequest, review_id)
        if review is None or review.job_id != job_id:
            raise AppError(ErrorCode.JOB_NOT_FOUND, "审核请求不存在", status_code=404)
        if review.status != ReviewStatus.PENDING.value:
            raise AppError(ErrorCode.INVALID_STATE, "审核请求已处理", status_code=409)
        job = self.db.get(TranslationJob, job_id)
        if job is None:
            raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
        allowed = {
            JobStatus.WAITING_RISK_REVIEW.value,
            JobStatus.WAITING_CHAPTER_REVIEW.value,
        }
        if job.status not in allowed:
            raise AppError(ErrorCode.INVALID_STATE, status_code=409)
        now = datetime.now(timezone.utc)
        review.status = ReviewStatus.APPROVED.value
        review.resolution_note = note
        review.resolved_at = now
        job.status = JobStatus.TRANSLATING.value
        job.current_stage = "review_approved"
        job.updated_at = now
        self.db.commit()
        return review
