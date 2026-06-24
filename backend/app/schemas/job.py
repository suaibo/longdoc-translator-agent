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
    status: str
    current_stage: str
    total_chunks: int
    completed_chunks: int
    progress_percent: float
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
