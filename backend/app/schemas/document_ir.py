from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.job import to_camel
from app.schemas.parser import BlockBoundingBox, BlockRisk


class IRModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SourceIR(IRModel):
    filename: str
    media_type: str


class SectionIR(IRModel):
    section_id: str
    title: str
    level: int
    path: list[str]
    parent_section_id: str | None = None
    heading_block_id: str


class TableCellIR(IRModel):
    row: int
    column: int
    text: str
    row_span: int = 1
    column_span: int = 1
    is_header: bool = False


class TableIR(IRModel):
    table_id: str
    caption: str | None = None
    cells: list[TableCellIR] = Field(default_factory=list)
    footnotes: list[str] = Field(default_factory=list)
    page_range: list[int] = Field(default_factory=list)
    confidence: float | None = None
    source_asset_id: str | None = None
    render_mode: Literal["GFM", "HTML", "IMAGE"] = "GFM"


class FormulaIR(IRModel):
    formula_id: str
    latex: str
    number: str | None = None
    page_no: int | None = None
    bbox: BlockBoundingBox | None = None
    confidence: float | None = None
    source_asset_id: str | None = None


class FigureIR(IRModel):
    figure_id: str
    caption: str | None = None
    page_no: int | None = None
    bbox: BlockBoundingBox | None = None
    source_asset_id: str | None = None
    references: list[str] = Field(default_factory=list)


class AssetIR(IRModel):
    asset_id: str
    kind: Literal["table", "formula", "figure"]
    relative_path: str | None = None
    media_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BlockIR(IRModel):
    block_id: str
    kind: str
    text: str
    markdown: str
    order: int
    section_id: str | None = None
    section_path: list[str] = Field(default_factory=list)
    page_no: int | None = None
    bbox: BlockBoundingBox | None = None
    heading_level: int | None = None
    structure: dict[str, Any] = Field(default_factory=dict)
    asset_ids: list[str] = Field(default_factory=list)
    risks: list[BlockRisk] = Field(default_factory=list)


class DocumentIR(IRModel):
    version: str = "1"
    job_id: str
    source: SourceIR
    sections: list[SectionIR] = Field(default_factory=list)
    blocks: list[BlockIR] = Field(default_factory=list)
    tables: list[TableIR] = Field(default_factory=list)
    formulas: list[FormulaIR] = Field(default_factory=list)
    figures: list[FigureIR] = Field(default_factory=list)
    assets: list[AssetIR] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)
