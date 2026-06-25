import re
from collections.abc import Callable
from gc import collect
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.schemas.parser import BlockBoundingBox, BlockKind, ParsedBlock
from app.services.layout_normalizer import LayoutNormalizer


class ParserService:
    def __init__(
        self,
        normalizer: LayoutNormalizer | None = None,
        converter_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.normalizer = normalizer or LayoutNormalizer()
        self.has_custom_converter = converter_factory is not None
        self.converter_factory = converter_factory or self._build_docling_converter

    def parse(
        self,
        source: Path,
        ocr_mode: str = "auto",
        assets_dir: Path | None = None,
    ) -> list[ParsedBlock]:
        extension = source.suffix.lower()
        if ocr_mode not in {"auto", "off", "force"}:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "ocrMode 必须是 auto、off 或 force",
                status_code=422,
            )
        try:
            if extension == ".pdf":
                blocks = self._parse_pdf(source, ocr_mode, assets_dir)
            elif extension == ".md":
                blocks = self._parse_markdown(source.read_text(encoding="utf-8-sig"))
            elif extension == ".txt":
                blocks = self._parse_text(source.read_text(encoding="utf-8-sig"))
            else:
                raise AppError(ErrorCode.UNSUPPORTED_FILE_TYPE, status_code=400)
            return self.normalizer.normalize(blocks)
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                ErrorCode.DOCLING_PARSE_FAILED,
                message=f"文档解析失败: {exc}",
                status_code=500,
            ) from exc

    def render_markdown(self, blocks: list[ParsedBlock]) -> str:
        content = "\n\n".join(
            block.markdown.strip() for block in blocks if block.markdown.strip()
        )
        return content + "\n"

    def parse_to_markdown(
        self,
        source: Path,
        destination: Path,
        ocr_mode: str = "auto",
        assets_dir: Path | None = None,
    ) -> list[ParsedBlock]:
        blocks = self.parse(source, ocr_mode=ocr_mode, assets_dir=assets_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(self.render_markdown(blocks), encoding="utf-8")
        # Replace only after the full document is written, so workers never read a partial file.
        temporary.replace(destination)
        return blocks

    def _parse_pdf(
        self, source: Path, ocr_mode: str, assets_dir: Path | None
    ) -> list[ParsedBlock]:
        if self.has_custom_converter:
            result = self.converter_factory(ocr_mode).convert(
                source, raises_on_error=True
            )
            return self._docling_blocks(result.document, assets_dir)

        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(source)
        page_count = len(pdf)
        pdf.close()
        blocks: list[ParsedBlock] = []
        batch_size = max(1, get_settings().docling_page_batch_size)
        for page_start in range(1, page_count + 1, batch_size):
            page_end = min(page_count, page_start + batch_size - 1)
            converter = self.converter_factory(ocr_mode)
            result = converter.convert(
                source,
                raises_on_error=True,
                page_range=(page_start, page_end),
            )
            blocks.extend(
                self._docling_blocks(
                    result.document,
                    assets_dir,
                    start_index=len(blocks),
                )
            )
            # Native page buffers can accumulate on Windows. Releasing each
            # batch prevents later pages from failing with std::bad_alloc.
            del result, converter
            collect()
        return blocks

    def _docling_blocks(
        self,
        document: Any,
        assets_dir: Path | None,
        *,
        start_index: int = 0,
    ) -> list[ParsedBlock]:
        blocks: list[ParsedBlock] = []
        for index, (item, depth) in enumerate(
            document.iterate_items(), start=start_index
        ):
            label = item.label.value
            kind = self._kind_from_docling_label(label)
            text = getattr(item, "text", "") or ""
            markdown = item.export_to_markdown(document) if label == "table" else text
            if kind == BlockKind.HEADING:
                level = getattr(item, "level", max(1, depth))
                markdown = f"{'#' * min(level, 6)} {text}"
            elif kind == BlockKind.TITLE:
                level = 1
                markdown = f"# {text}"
            elif kind == BlockKind.LIST_ITEM:
                level = None
                markdown = f"{getattr(item, 'marker', '-')} {text}"
            elif kind == BlockKind.FORMULA:
                level = None
                markdown = text if text.startswith("$") else f"$$\n{text}\n$$"
            else:
                level = None

            page_no, bbox = self._docling_position(document, item)
            block_id = f"block_{index:06d}"
            asset_metadata = self._save_source_asset(
                document, item, kind, block_id, assets_dir
            )
            blocks.append(
                ParsedBlock(
                    block_id=block_id,
                    kind=kind,
                    text=text or markdown,
                    markdown=markdown,
                    page_no=page_no,
                    bbox=bbox,
                    heading_level=level,
                    metadata={
                        "docling_label": label,
                        "docling_depth": depth,
                        "docling_self_ref": getattr(item, "self_ref", None),
                        "docling_parent_ref": getattr(
                            getattr(item, "parent", None), "cref", None
                        ),
                        "docling_caption_refs": [
                            getattr(reference, "cref", None)
                            for reference in getattr(item, "captions", [])
                        ],
                        **asset_metadata,
                    },
                )
            )
        return blocks

    def _parse_markdown(self, content: str) -> list[ParsedBlock]:
        lines = content.replace("\r\n", "\n").split("\n")
        blocks: list[ParsedBlock] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if not line.strip():
                index += 1
                continue

            heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading:
                blocks.append(
                    self._text_block(
                        blocks,
                        BlockKind.TITLE
                        if len(heading.group(1)) == 1 and not blocks
                        else BlockKind.HEADING,
                        heading.group(2).strip(),
                        line,
                        heading_level=len(heading.group(1)),
                    )
                )
                index += 1
                continue

            if line.lstrip().startswith("```"):
                chunk, index = self._consume_fenced(lines, index, "```")
                blocks.append(
                    self._text_block(
                        blocks, BlockKind.CODE, "\n".join(chunk[1:-1]), "\n".join(chunk)
                    )
                )
                continue

            if line.strip().startswith("$$"):
                chunk, index = self._consume_formula(lines, index)
                blocks.append(
                    self._text_block(
                        blocks, BlockKind.FORMULA, "\n".join(chunk), "\n".join(chunk)
                    )
                )
                continue

            if self._starts_table(lines, index):
                chunk, index = self._consume_table(lines, index)
                markdown = "\n".join(chunk)
                blocks.append(
                    self._text_block(blocks, BlockKind.TABLE, markdown, markdown)
                )
                continue

            if self._is_caption(line):
                caption = line.strip()
                blocks.append(
                    self._text_block(blocks, BlockKind.CAPTION, caption, caption)
                )
                index += 1
                continue

            list_item = re.match(r"^\s*((?:[-*+])|(?:\d+\.))\s+(.+)$", line)
            if list_item:
                blocks.append(
                    self._text_block(
                        blocks, BlockKind.LIST_ITEM, list_item.group(2), line
                    )
                )
                index += 1
                continue

            paragraph, index = self._consume_paragraph(lines, index)
            text = "\n".join(paragraph).strip()
            blocks.append(self._text_block(blocks, BlockKind.PARAGRAPH, text, text))
        return blocks

    def _parse_text(self, content: str) -> list[ParsedBlock]:
        paragraphs = re.split(r"\n\s*\n", content.replace("\r\n", "\n"))
        return [
            self._text_block(
                [],
                BlockKind.PARAGRAPH,
                paragraph.strip(),
                paragraph.strip(),
                block_index=index,
            )
            for index, paragraph in enumerate(paragraphs)
            if paragraph.strip()
        ]

    @staticmethod
    def _build_docling_converter(ocr_mode: str) -> Any:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            RapidOcrOptions,
            TableStructureV2Options,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption

        options = PdfPipelineOptions()
        artifacts_path = ParserService._resolve_docling_artifacts_path()
        if artifacts_path is not None:
            options.artifacts_path = artifacts_path
        # The downloaded artifacts use TableFormerV2. Selecting it explicitly
        # prevents Docling from looking for the legacy accurate/tm_config.json.
        options.table_structure_options = TableStructureV2Options()
        options.do_ocr = ocr_mode != "off"
        options.generate_page_images = True
        options.generate_picture_images = True
        options.generate_table_images = True
        options.images_scale = 2.0
        ocr_engine = get_settings().ocr_engine
        if options.do_ocr and ocr_engine == "rapidocr-onnxruntime":
            # Pin the OCR backend so an installed torch package cannot make RapidOCR
            # select an unsupported PP-OCR model combination at runtime.
            options.ocr_options = RapidOcrOptions(
                backend="onnxruntime",
                force_full_page_ocr=ocr_mode == "force",
                lang=["english"],
            )
        elif options.do_ocr and ocr_engine != "docling-auto":
            raise ValueError(f"unsupported OCR_ENGINE: {ocr_engine}")
        return DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
        )

    @staticmethod
    def _resolve_docling_artifacts_path() -> Path | None:
        configured = get_settings().docling_artifacts_path
        candidate = configured or Path.home() / ".cache" / "docling" / "models"
        required = (
            "docling-project--docling-layout-heron",
            "docling-project--TableFormerV2",
            "RapidOcr",
        )
        if candidate.is_dir() and all((candidate / name).is_dir() for name in required):
            return candidate
        return None

    @staticmethod
    def _save_source_asset(
        document: Any,
        item: Any,
        kind: BlockKind,
        block_id: str,
        assets_dir: Path | None,
    ) -> dict[str, Any]:
        if (
            assets_dir is None
            or kind not in {BlockKind.TABLE, BlockKind.FORMULA, BlockKind.PICTURE}
            or not hasattr(item, "get_image")
        ):
            return {}
        try:
            image = item.get_image(document)
            if image is None:
                return {}
            category = {
                BlockKind.TABLE: "tables",
                BlockKind.FORMULA: "formulas",
                BlockKind.PICTURE: "figures",
            }[kind]
            destination = assets_dir / category / f"{block_id}.png"
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(".png.tmp")
            image.save(temporary, format="PNG")
            temporary.replace(destination)
            return {
                "source_asset_path": destination.relative_to(
                    assets_dir.parent
                ).as_posix(),
                "source_asset_media_type": "image/png",
            }
        except Exception as exc:
            return {"source_asset_error": str(exc)}

    @staticmethod
    def _docling_position(
        document: Any, item: Any
    ) -> tuple[int | None, BlockBoundingBox | None]:
        if not getattr(item, "prov", None):
            return None, None
        provenance = item.prov[0]
        page = document.pages.get(provenance.page_no)
        if page is None:
            return provenance.page_no, None
        bbox = provenance.bbox.to_top_left_origin(page.size.height)
        return provenance.page_no, BlockBoundingBox(
            left=bbox.l,
            top=bbox.t,
            right=bbox.r,
            bottom=bbox.b,
            page_width=page.size.width,
            page_height=page.size.height,
        )

    @staticmethod
    def _kind_from_docling_label(label: str) -> BlockKind:
        mapping = {
            "title": BlockKind.TITLE,
            "section_header": BlockKind.HEADING,
            "text": BlockKind.PARAGRAPH,
            "paragraph": BlockKind.PARAGRAPH,
            "list_item": BlockKind.LIST_ITEM,
            "table": BlockKind.TABLE,
            "formula": BlockKind.FORMULA,
            "caption": BlockKind.CAPTION,
            "reference": BlockKind.REFERENCE,
            "picture": BlockKind.PICTURE,
            "code": BlockKind.CODE,
            "page_header": BlockKind.OTHER,
            "page_footer": BlockKind.OTHER,
        }
        return mapping.get(label, BlockKind.OTHER)

    @staticmethod
    def _text_block(
        blocks: list[ParsedBlock],
        kind: BlockKind,
        text: str,
        markdown: str,
        heading_level: int | None = None,
        block_index: int | None = None,
    ) -> ParsedBlock:
        index = len(blocks) if block_index is None else block_index
        return ParsedBlock(
            block_id=f"block_{index:06d}",
            kind=kind,
            text=text,
            markdown=markdown,
            heading_level=heading_level,
        )

    @staticmethod
    def _is_caption(line: str) -> bool:
        return bool(
            re.match(
                r"^\s*(?:(?:Table|Figure|Fig\.)\s+\d+\s*[.:]|[表图]\s*\d+\s*[：:.])\s*.+$",
                line,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _starts_table(lines: list[str], index: int) -> bool:
        if index + 1 >= len(lines) or "|" not in lines[index]:
            return False
        return bool(re.match(r"^\s*\|?\s*:?-{3,}", lines[index + 1]))

    @staticmethod
    def _consume_table(lines: list[str], index: int) -> tuple[list[str], int]:
        chunk: list[str] = []
        while index < len(lines) and lines[index].strip() and "|" in lines[index]:
            chunk.append(lines[index])
            index += 1
        return chunk, index

    @staticmethod
    def _consume_fenced(
        lines: list[str], index: int, fence: str
    ) -> tuple[list[str], int]:
        chunk = [lines[index]]
        index += 1
        while index < len(lines):
            chunk.append(lines[index])
            index += 1
            if chunk[-1].lstrip().startswith(fence):
                break
        return chunk, index

    @staticmethod
    def _consume_formula(lines: list[str], index: int) -> tuple[list[str], int]:
        chunk = [lines[index]]
        if lines[index].strip().count("$$") >= 2:
            return chunk, index + 1
        index += 1
        while index < len(lines):
            chunk.append(lines[index])
            index += 1
            if "$$" in chunk[-1]:
                break
        return chunk, index

    def _consume_paragraph(self, lines: list[str], index: int) -> tuple[list[str], int]:
        chunk: list[str] = []
        while index < len(lines) and lines[index].strip():
            if chunk and (
                re.match(r"^#{1,6}\s+", lines[index])
                or lines[index].lstrip().startswith("```")
                or lines[index].strip().startswith("$$")
                or self._starts_table(lines, index)
            ):
                break
            chunk.append(lines[index])
            index += 1
        return chunk, index
