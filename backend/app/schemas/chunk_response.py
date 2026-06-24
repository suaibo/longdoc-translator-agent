from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.job import to_camel


class ChunkResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    chunk_id: str
    chunk_index: int
    section_title: str | None
    section_path: list[str]
    chunk_type: str
    status: str
    has_risk: bool
    risk_types: list[str]
    risk_summary: str | None
    source_preview: str
    translated_preview: str | None
    boundary_reason: str | None
    boundary_score: float | None
    semantic_topic: str | None
    translated_at: datetime | None
