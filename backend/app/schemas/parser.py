from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import RiskType


class BlockKind(StrEnum):
    TITLE = "title"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    FORMULA = "formula"
    CAPTION = "caption"
    REFERENCE = "reference"
    PICTURE = "picture"
    CODE = "code"
    OTHER = "other"


class BlockBoundingBox(BaseModel):
    left: float
    top: float
    right: float
    bottom: float
    page_width: float
    page_height: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2


class BlockRisk(BaseModel):
    risk_type: RiskType
    message: str


class ParsedBlock(BaseModel):
    block_id: str
    kind: BlockKind
    text: str
    markdown: str
    order: int = 0
    page_no: int | None = None
    bbox: BlockBoundingBox | None = None
    heading_level: int | None = None
    risks: list[BlockRisk] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
