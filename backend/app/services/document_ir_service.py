import csv
import hashlib
import mimetypes
import re
from pathlib import Path
from typing import Any

from app.schemas.document_ir import (
    AssetIR,
    BlockIR,
    DocumentIR,
    FigureIR,
    FormulaIR,
    SectionIR,
    SourceIR,
    TableCellIR,
    TableIR,
)
from app.schemas.parser import BlockKind, ParsedBlock


class DocumentIRService:
    VERSION = "1"

    def build(
        self,
        job_id: str,
        original_filename: str,
        blocks: list[ParsedBlock],
        assets_dir: Path,
    ) -> DocumentIR:
        sections: list[SectionIR] = []
        block_irs: list[BlockIR] = []
        tables: list[TableIR] = []
        formulas: list[FormulaIR] = []
        figures: list[FigureIR] = []
        assets: list[AssetIR] = []
        heading_stack: list[SectionIR] = []

        assets_dir.mkdir(parents=True, exist_ok=True)
        for block in sorted(blocks, key=lambda item: item.order):
            if block.kind in {BlockKind.TITLE, BlockKind.HEADING}:
                level = block.heading_level or (1 if block.kind == BlockKind.TITLE else 2)
                while heading_stack and heading_stack[-1].level >= level:
                    heading_stack.pop()
                path = [section.title for section in heading_stack] + [block.text.strip()]
                section = SectionIR(
                    section_id=self._stable_id("section", *path, block.block_id),
                    title=block.text.strip(),
                    level=level,
                    path=path,
                    parent_section_id=heading_stack[-1].section_id if heading_stack else None,
                    heading_block_id=block.block_id,
                )
                sections.append(section)
                heading_stack.append(section)

            current = heading_stack[-1] if heading_stack else None
            asset_ids: list[str] = []
            structure = dict(block.metadata)
            source_asset = self._source_asset(block)
            if source_asset:
                assets.append(source_asset)
                asset_ids.append(source_asset.asset_id)
            if block.kind == BlockKind.TABLE:
                table, asset = self._table_ir(
                    block,
                    assets_dir,
                    source_asset.asset_id if source_asset else None,
                )
                tables.append(table)
                if asset:
                    assets.append(asset)
                    asset_ids.append(asset.asset_id)
                structure["tableId"] = table.table_id
            elif block.kind == BlockKind.FORMULA:
                formula = self._formula_ir(
                    block, source_asset.asset_id if source_asset else None
                )
                formulas.append(formula)
                structure["formulaId"] = formula.formula_id
            elif block.kind == BlockKind.PICTURE:
                figure = self._figure_ir(
                    block, source_asset.asset_id if source_asset else None
                )
                figures.append(figure)
                structure["figureId"] = figure.figure_id

            block_irs.append(
                BlockIR(
                    block_id=block.block_id,
                    kind=block.kind.value,
                    text=block.text,
                    markdown=block.markdown,
                    order=block.order,
                    section_id=current.section_id if current else None,
                    section_path=current.path if current else [],
                    page_no=block.page_no,
                    bbox=block.bbox,
                    heading_level=block.heading_level,
                    structure=structure,
                    asset_ids=asset_ids,
                    risks=block.risks,
                )
            )

        return DocumentIR(
            version=self.VERSION,
            job_id=job_id,
            source=SourceIR(
                filename=original_filename,
                media_type=mimetypes.guess_type(original_filename)[0]
                or "application/octet-stream",
            ),
            sections=sections,
            blocks=block_irs,
            tables=tables,
            formulas=formulas,
            figures=figures,
            assets=assets,
            risks=[
                {
                    "blockId": block.block_id,
                    "type": risk.risk_type.value,
                    "message": risk.message,
                }
                for block in blocks
                for risk in block.risks
            ],
        )

    def write(self, document: DocumentIR, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(
            document.model_dump_json(indent=2, by_alias=True),
            encoding="utf-8",
        )
        temporary.replace(destination)

    def read(self, source: Path) -> DocumentIR:
        document = DocumentIR.model_validate_json(source.read_text(encoding="utf-8"))
        if document.version != self.VERSION:
            raise ValueError(
                f"unsupported DocumentIR version {document.version}; "
                f"expected {self.VERSION}"
            )
        return document

    def to_parsed_blocks(self, document: DocumentIR) -> list[ParsedBlock]:
        return [
            ParsedBlock(
                block_id=block.block_id,
                kind=BlockKind(block.kind),
                text=block.text,
                markdown=block.markdown,
                order=block.order,
                page_no=block.page_no,
                bbox=block.bbox,
                heading_level=block.heading_level,
                risks=block.risks,
                metadata={
                    **block.structure,
                    "section_id": block.section_id,
                    "section_path": block.section_path,
                    "asset_ids": block.asset_ids,
                },
            )
            for block in document.blocks
        ]

    def _table_ir(
        self,
        block: ParsedBlock,
        assets_dir: Path,
        source_image_asset_id: str | None,
    ) -> tuple[TableIR, AssetIR | None]:
        table_id = self._stable_id("table", block.block_id)
        rows = self._parse_markdown_table(block.markdown)
        cells = [
            TableCellIR(
                row=row_index,
                column=column_index,
                text=value,
                is_header=row_index == 0,
            )
            for row_index, row in enumerate(rows)
            for column_index, value in enumerate(row)
        ]
        page_range = [block.page_no] if block.page_no is not None else []
        confidence = self._confidence(block.metadata)
        render_mode = (
            "IMAGE"
            if confidence is not None and confidence < 0.6
            else "GFM"
            if rows and len(rows[0]) <= 8
            else "HTML"
        )
        asset = None
        source_asset_id = source_image_asset_id
        if rows:
            table_dir = assets_dir / "tables"
            table_dir.mkdir(parents=True, exist_ok=True)
            csv_path = table_dir / f"{table_id}.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as file:
                csv.writer(file).writerows(rows)
            csv_asset_id = f"asset_{table_id}_csv"
            asset = AssetIR(
                asset_id=csv_asset_id,
                kind="table",
                relative_path=csv_path.relative_to(assets_dir.parent).as_posix(),
                media_type="text/csv",
                metadata={"blockId": block.block_id},
            )
        return (
            TableIR(
                table_id=table_id,
                cells=cells,
                page_range=page_range,
                confidence=confidence,
                source_asset_id=source_asset_id or (asset.asset_id if asset else None),
                render_mode=render_mode,
            ),
            asset,
        )

    def _formula_ir(
        self, block: ParsedBlock, source_asset_id: str | None
    ) -> FormulaIR:
        latex = re.sub(r"^\$\$|\$\$$", "", block.markdown.strip()).strip()
        number_match = re.search(r"\((\d+(?:\.\d+)*)\)\s*$", latex)
        return FormulaIR(
            formula_id=self._stable_id("formula", block.block_id),
            latex=latex,
            number=number_match.group(1) if number_match else None,
            page_no=block.page_no,
            bbox=block.bbox,
            confidence=self._confidence(block.metadata),
            source_asset_id=source_asset_id,
        )

    def _figure_ir(
        self, block: ParsedBlock, source_asset_id: str | None
    ) -> FigureIR:
        return FigureIR(
            figure_id=self._stable_id("figure", block.block_id),
            caption=block.text or None,
            page_no=block.page_no,
            bbox=block.bbox,
            source_asset_id=source_asset_id,
            references=[
                str(value)
                for value in block.metadata.get("docling_caption_refs", [])
                if value
            ],
        )

    @staticmethod
    def _source_asset(block: ParsedBlock) -> AssetIR | None:
        path = block.metadata.get("source_asset_path")
        if not isinstance(path, str):
            return None
        kind = {
            BlockKind.TABLE: "table",
            BlockKind.FORMULA: "formula",
            BlockKind.PICTURE: "figure",
        }.get(block.kind)
        if kind is None:
            return None
        return AssetIR(
            asset_id=f"asset_{block.block_id}_source",
            kind=kind,
            relative_path=path,
            media_type=str(
                block.metadata.get("source_asset_media_type", "application/octet-stream")
            ),
            metadata={"blockId": block.block_id, "sourceEvidence": True},
        )

    @staticmethod
    def _parse_markdown_table(markdown: str) -> list[list[str]]:
        lines = [line.strip() for line in markdown.splitlines() if "|" in line]
        if len(lines) < 2:
            return []
        rows: list[list[str]] = []
        for index, line in enumerate(lines):
            values = [value.strip() for value in line.strip("|").split("|")]
            if index == 1 and all(re.fullmatch(r":?-{3,}:?", value) for value in values):
                continue
            rows.append(values)
        return rows

    @staticmethod
    def _confidence(metadata: dict[str, Any]) -> float | None:
        value = metadata.get("confidence")
        return float(value) if isinstance(value, int | float) else None

    @staticmethod
    def _stable_id(prefix: str, *parts: str) -> str:
        digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:24]
        return f"{prefix}_{digest}"
