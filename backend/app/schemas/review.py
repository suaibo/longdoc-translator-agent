from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.job import to_camel


class ApproveReviewRequest(BaseModel):
    note: str | None = None


class ReviewResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    review_id: str
    review_type: str
    subject_id: str
    status: str
    payload: dict[str, Any]
    resolution_note: str | None
    created_at: datetime
    resolved_at: datetime | None
