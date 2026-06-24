from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ChunkType
from app.schemas.parser import BlockRisk


class ChunkDraft(BaseModel):
    chunk_index: int = 0
    section_title: str | None = None
    chunk_type: ChunkType = ChunkType.TEXT
    source_text: str
    source_block_ids: list[str] = Field(default_factory=list)
    structure_metadata: dict[str, Any] = Field(default_factory=dict)
    section_path: list[str] = Field(default_factory=list)
    boundary_reason: str | None = None
    boundary_score: float | None = None
    semantic_topic: str | None = None
    risks: list[BlockRisk] = Field(default_factory=list)
    token_estimate: int = 0
