from pathlib import Path

import pytest

from app.schemas.parser import BlockKind, ParsedBlock
from app.services.document_ir_service import DocumentIRService


def test_document_ir_builds_section_paths_and_table_asset(tmp_path: Path) -> None:
    blocks = [
        ParsedBlock(
            block_id="h1",
            kind=BlockKind.TITLE,
            text="Paper",
            markdown="# Paper",
            heading_level=1,
            order=0,
        ),
        ParsedBlock(
            block_id="h2",
            kind=BlockKind.HEADING,
            text="Method",
            markdown="## Method",
            heading_level=2,
            order=1,
        ),
        ParsedBlock(
            block_id="p1",
            kind=BlockKind.PARAGRAPH,
            text="Body",
            markdown="Body",
            order=2,
        ),
        ParsedBlock(
            block_id="t1",
            kind=BlockKind.TABLE,
            text="| A | B |\n| --- | --- |\n| 1 | 2 |",
            markdown="| A | B |\n| --- | --- |\n| 1 | 2 |",
            order=3,
        ),
    ]
    service = DocumentIRService()
    document = service.build("job_ir", "paper.md", blocks, tmp_path / "assets")
    destination = tmp_path / "document.ir.json"
    service.write(document, destination)
    restored = service.read(destination)

    assert restored.sections[-1].path == ["Paper", "Method"]
    assert restored.blocks[2].section_path == ["Paper", "Method"]
    assert restored.tables[0].cells[0].is_header is True
    assert restored.assets[0].relative_path.startswith("assets/tables/")
    assert (tmp_path / restored.assets[0].relative_path).is_file()


def test_document_ir_rejects_incompatible_version(tmp_path: Path) -> None:
    path = tmp_path / "document.ir.json"
    path.write_text(
        '{"version":"999","jobId":"x","source":{"filename":"x.md","media_type":"text/markdown"}}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported DocumentIR version"):
        DocumentIRService().read(path)
