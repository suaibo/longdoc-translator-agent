from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.errors import AppError, ErrorCode
from app.models.enums import RiskType
from app.schemas.parser import BlockBoundingBox, BlockKind, ParsedBlock
from app.services.layout_normalizer import LayoutNormalizer
from app.services.parser_service import ParserService


def make_block(
    block_id: str,
    text: str,
    page_no: int,
    left: float,
    top: float,
    right: float,
    bottom: float,
    *,
    label: str = "text",
) -> ParsedBlock:
    return ParsedBlock(
        block_id=block_id,
        kind=BlockKind.PARAGRAPH,
        text=text,
        markdown=text,
        page_no=page_no,
        bbox=BlockBoundingBox(
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            page_width=600,
            page_height=800,
        ),
        metadata={"docling_label": label},
    )


def risk_types(block: ParsedBlock) -> set[RiskType]:
    return {risk.risk_type for risk in block.risks}


def test_markdown_creates_structured_table_formula_and_long_paragraph(
    tmp_path: Path,
) -> None:
    source = tmp_path / "paper.md"
    source.write_text(
        "# Paper\n\n"
        "| Method | Score |\n| --- | --- |\n| A | 0.9 |\n\n"
        "The objective is $L = x^2$.\n\n" + "A" * 40,
        encoding="utf-8",
    )
    service = ParserService(normalizer=LayoutNormalizer(long_paragraph_chars=20))

    blocks = service.parse(source)

    assert [block.kind for block in blocks] == [
        BlockKind.TITLE,
        BlockKind.TABLE,
        BlockKind.PARAGRAPH,
        BlockKind.PARAGRAPH,
    ]
    table = blocks[1]
    assert table.markdown.count("\n") == 2
    assert RiskType.TABLE in risk_types(table)
    assert RiskType.FORMULA in risk_types(blocks[2])
    assert RiskType.LONG_PARAGRAPH in risk_types(blocks[3])


def test_txt_paragraphs_share_the_same_block_model(tmp_path: Path) -> None:
    source = tmp_path / "paper.txt"
    source.write_text("First paragraph.\n\nSecond paragraph.", encoding="utf-8")

    blocks = ParserService().parse(source)

    assert [block.text for block in blocks] == ["First paragraph.", "Second paragraph."]
    assert all(block.kind == BlockKind.PARAGRAPH for block in blocks)
    assert [block.order for block in blocks] == [0, 1]


def test_two_column_layout_is_reordered_left_then_right() -> None:
    blocks = [
        make_block("left-1", "L1", 1, 40, 100, 270, 160),
        make_block("right-1", "R1", 1, 330, 100, 560, 160),
        make_block("left-2", "L2", 1, 40, 180, 270, 240),
        make_block("right-2", "R2", 1, 330, 180, 560, 240),
    ]

    normalized = LayoutNormalizer().normalize(blocks)

    assert [block.text for block in normalized] == ["L1", "L2", "R1", "R2"]
    assert all(RiskType.STRUCTURE in risk_types(block) for block in normalized)


def test_repeated_and_explicit_headers_and_footers_are_removed() -> None:
    blocks = [
        make_block("header-1", "Journal Name", 1, 50, 10, 550, 35),
        make_block("body-1", "Page one", 1, 50, 150, 550, 220),
        make_block("footer-1", "1", 1, 280, 760, 320, 785, label="page_footer"),
        make_block("header-2", "Journal Name", 2, 50, 10, 550, 35),
        make_block("body-2", "Page two", 2, 50, 150, 550, 220),
        make_block("footer-2", "2", 2, 280, 760, 320, 785, label="page_footer"),
    ]

    normalized = LayoutNormalizer().normalize(blocks)

    assert [block.text for block in normalized] == ["Page one", "Page two"]


def test_reference_dense_paragraph_is_marked(tmp_path: Path) -> None:
    source = tmp_path / "references.md"
    source.write_text(
        "Prior work [1] established this; later work [2] refined it.", encoding="utf-8"
    )

    blocks = ParserService().parse(source)

    assert RiskType.REFERENCE in risk_types(blocks[0])


def test_same_page_duplicate_edge_text_is_not_treated_as_repeated_header() -> None:
    blocks = [
        make_block("note-1", "Draft", 1, 50, 10, 550, 35),
        make_block("note-2", "Draft", 1, 50, 40, 550, 65),
        make_block("body", "Body", 1, 50, 150, 550, 220),
    ]

    normalized = LayoutNormalizer().normalize(blocks)

    assert [block.text for block in normalized] == ["Draft", "Draft", "Body"]


def test_full_width_blocks_split_two_column_segments() -> None:
    title = make_block("title", "Title", 1, 30, 20, 570, 70)
    table = make_block("table", "Table", 1, 30, 280, 570, 340).model_copy(
        update={"kind": BlockKind.TABLE}
    )
    blocks = [
        title,
        make_block("left-1", "L1", 1, 40, 100, 270, 160),
        make_block("right-1", "R1", 1, 330, 100, 560, 160),
        table,
        make_block("left-2", "L2", 1, 40, 380, 270, 440),
        make_block("right-2", "R2", 1, 330, 380, 560, 440),
    ]

    normalized = LayoutNormalizer().normalize(blocks)

    assert [block.text for block in normalized] == [
        "Title",
        "L1",
        "R1",
        "Table",
        "L2",
        "R2",
    ]


def test_parse_to_markdown_writes_complete_document(tmp_path: Path) -> None:
    source = tmp_path / "paper.md"
    destination = tmp_path / "parsed" / "document.md"
    source.write_text("# Paper\n\nBody text.", encoding="utf-8")

    blocks = ParserService().parse_to_markdown(source, destination)

    assert len(blocks) == 2
    assert destination.read_text(encoding="utf-8") == "# Paper\n\nBody text.\n"
    assert not destination.with_suffix(".md.tmp").exists()


def test_docling_pdf_items_map_to_parsed_blocks(tmp_path: Path) -> None:
    class FakeBBox:
        l = 20  # noqa: E741
        t = 30
        r = 580
        b = 180

        def to_top_left_origin(self, page_height: float):
            assert page_height == 800
            return self

    class FakeTable:
        label = SimpleNamespace(value="table")
        text = "Method Score"
        prov = [SimpleNamespace(page_no=1, bbox=FakeBBox())]

        @staticmethod
        def export_to_markdown(document) -> str:
            return "| Method | Score |\n| --- | --- |\n| A | 0.9 |"

    document = SimpleNamespace(
        pages={1: SimpleNamespace(size=SimpleNamespace(width=600, height=800))},
        iterate_items=lambda: iter([(FakeTable(), 1)]),
    )
    converter = SimpleNamespace(
        convert=lambda source, raises_on_error: SimpleNamespace(document=document)
    )
    service = ParserService(converter_factory=lambda ocr_mode: converter)
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-fake")

    blocks = service.parse(source, ocr_mode="off")

    assert len(blocks) == 1
    assert blocks[0].kind == BlockKind.TABLE
    assert blocks[0].bbox is not None
    assert blocks[0].bbox.page_width == 600
    assert RiskType.TABLE in risk_types(blocks[0])


def test_bad_pdf_returns_docling_parse_error(tmp_path: Path) -> None:
    class BrokenConverter:
        @staticmethod
        def convert(source, raises_on_error):
            raise ValueError("invalid xref table")

    source = tmp_path / "bad.pdf"
    source.write_bytes(b"not a pdf")
    service = ParserService(converter_factory=lambda ocr_mode: BrokenConverter())

    with pytest.raises(AppError) as caught:
        service.parse(source)

    assert caught.value.code == ErrorCode.DOCLING_PARSE_FAILED
    assert caught.value.status_code == 500
    assert "invalid xref table" in caught.value.message


def test_invalid_ocr_mode_is_validation_error(tmp_path: Path) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"pdf")

    with pytest.raises(AppError) as caught:
        ParserService().parse(source, ocr_mode="sometimes")

    assert caught.value.code == ErrorCode.VALIDATION_ERROR


def test_docling_converter_uses_stable_ocr_backend() -> None:
    from docling.datamodel.base_models import InputFormat

    automatic = ParserService._build_docling_converter("auto")
    forced = ParserService._build_docling_converter("force")
    disabled = ParserService._build_docling_converter("off")

    auto_options = automatic.format_to_options[InputFormat.PDF].pipeline_options
    force_options = forced.format_to_options[InputFormat.PDF].pipeline_options
    off_options = disabled.format_to_options[InputFormat.PDF].pipeline_options
    assert auto_options.ocr_options.backend == "onnxruntime"
    assert force_options.ocr_options.force_full_page_ocr is True
    assert off_options.do_ocr is False


def test_real_docling_rejects_malformed_pdf(tmp_path: Path) -> None:
    source = tmp_path / "malformed.pdf"
    source.write_bytes(b"not a pdf")

    with pytest.raises(AppError) as caught:
        ParserService().parse(source, ocr_mode="off")

    assert caught.value.code == ErrorCode.DOCLING_PARSE_FAILED
    assert "not valid" in caught.value.message
