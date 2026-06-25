from datetime import datetime

from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class JobResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    job_id: str
    original_filename: str
    mode: str
    source_language: str | None
    target_language: str
    status: str
    current_stage: str
    total_chunks: int
    completed_chunks: int
    progress_percent: float
    eta_seconds: int | None
    queue_position: int | None = None
    has_unresolved_risks: bool
    require_high_risk_review: bool
    require_chapter_review: bool
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class JobCreatedResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    job_id: str


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    job_id: str
    status: str
