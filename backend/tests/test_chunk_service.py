import re
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.models.document_chunk import DocumentChunk
from app.models.enums import ChunkStatus, ChunkType, JobStatus, RiskType
from app.models.risk_item import RiskItem
from app.models.translation_job import TranslationJob
from app.schemas.parser import BlockKind, BlockRisk, ParsedBlock
from app.services.chunk_service import ChunkService
from app.services.parser_service import ParserService


def block(
    block_id: str,
    kind: BlockKind,
    markdown: str,
    order: int,
    *,
    page_no: int | None = None,
    risks: list[BlockRisk] | None = None,
    metadata: dict | None = None,
) -> ParsedBlock:
    return ParsedBlock(
        block_id=block_id,
        kind=kind,
        text=markdown.lstrip("# "),
        markdown=markdown,
        order=order,
        page_no=page_no,
        risks=risks or [],
        metadata=metadata or {},
    )


def add_job(db: Session, job_id: str = "job_chunks") -> TranslationJob:
    job = TranslationJob(
        job_id=job_id,
        original_filename="paper.md",
        original_file_path=f"storage/uploads/{job_id}/original.md",
        parsed_markdown_path=f"storage/parsed/{job_id}/document.md",
        mode="paper",
        status=JobStatus.UPLOADED.value,
        current_stage="uploaded",
        created_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
    )
    db.add(job)
    db.commit()
    return job


def test_build_drafts_preserves_section_boundaries(db_session: Session) -> None:
    blocks = [
        block("title", BlockKind.TITLE, "# Paper", 0),
        block("abstract", BlockKind.PARAGRAPH, "Abstract body.", 1),
        block("method", BlockKind.HEADING, "## Method", 2),
        block("method-body", BlockKind.PARAGRAPH, "Method body.", 3),
    ]

    drafts = ChunkService(db_session, max_tokens=100).build_drafts(blocks)

    assert len(drafts) == 2
    assert drafts[0].section_title == "Paper"
    assert drafts[0].source_text == "# Paper\n\nAbstract body."
    assert drafts[1].section_title == "Method"
    assert drafts[1].source_text == "## Method\n\nMethod body."


def test_long_paragraph_splits_only_at_sentence_boundaries(
    db_session: Session,
) -> None:
    text = (
        "First sentence explains the model. "
        "Second sentence keeps $E = mc^2$ and citation [2-4]. "
        "Third sentence closes the section."
    )
    blocks = [block("paragraph", BlockKind.PARAGRAPH, text, 0)]

    drafts = ChunkService(db_session, max_tokens=12).build_drafts(blocks)

    assert len(drafts) == 3
    assert drafts[0].source_text.endswith("model.")
    assert "$E = mc^2$" in drafts[1].source_text
    assert "[2-4]" in drafts[1].source_text
    assert all(draft.source_block_ids == ["paragraph"] for draft in drafts)


def test_chinese_sentence_split_does_not_insert_spaces(db_session: Session) -> None:
    text = "第一句介绍方法。第二句保留公式 $E=mc^2$。第三句给出结论。"
    blocks = [block("paragraph-cn", BlockKind.PARAGRAPH, text, 0)]

    drafts = ChunkService(db_session, max_tokens=16).build_drafts(blocks)

    assert len(drafts) == 3
    assert "".join(draft.source_text for draft in drafts) == text


def test_formula_and_code_are_atomic_even_above_limit(db_session: Session) -> None:
    formula = block(
        "formula",
        BlockKind.FORMULA,
        "$$\n" + "x" * 100 + "\n$$",
        0,
        metadata={"source_asset_path": "assets/formulas/formula.png"},
    )
    code = block("code", BlockKind.CODE, "```python\n" + "x = 1\n" * 20 + "```", 1)

    drafts = ChunkService(db_session, max_tokens=5).build_drafts([formula, code])

    assert [draft.chunk_type for draft in drafts] == [ChunkType.FORMULA, ChunkType.CODE]
    assert drafts[0].structure_metadata["atomic"] is True
    assert drafts[0].structure_metadata["translationProtected"] is True
    assert drafts[0].structure_metadata["sourceAssetPath"] == "assets/formulas/formula.png"
    assert drafts[1].structure_metadata["atomic"] is True


def test_small_table_and_caption_remain_one_atomic_chunk(db_session: Session) -> None:
    caption = block("caption", BlockKind.CAPTION, "Table 1. Results", 0)
    table = block(
        "table",
        BlockKind.TABLE,
        "| Method | Score |\n| --- | --- |\n| A | 0.9 |",
        1,
    )

    drafts = ChunkService(db_session, max_tokens=100, max_table_rows=5).build_drafts(
        [caption, table]
    )

    assert len(drafts) == 1
    assert drafts[0].chunk_type == ChunkType.TABLE
    assert drafts[0].source_block_ids == ["caption", "table"]
    assert drafts[0].source_text.startswith("Table 1. Results\n\n| Method")
    assert drafts[0].structure_metadata["groupCount"] == 1
    assert RiskType.TABLE in {risk.risk_type for risk in drafts[0].risks}


def test_author_contact_table_is_protected_from_translation(
    db_session: Session,
) -> None:
    table = block(
        "authors",
        BlockKind.TABLE,
        "| Ashish Vaswani Google Brain avaswani@google.com | Noam Shazeer Google Brain noam@google.com |\n"
        "| --- | --- |\n"
        "| Niki Parmar Google Research nikip@google.com | Jakob Uszkoreit Google Research usz@google.com |",
        0,
        page_no=1,
    )

    drafts = ChunkService(db_session, max_tokens=100).build_drafts([table])

    assert len(drafts) == 1
    assert drafts[0].chunk_type == ChunkType.TABLE
    assert drafts[0].structure_metadata["translationProtected"] is True
    assert drafts[0].structure_metadata["protectionReason"] == "author_contact_block"


def test_large_table_splits_by_rows_and_repeats_context(db_session: Session) -> None:
    caption = block("caption", BlockKind.CAPTION, "Table 2. Metrics", 0)
    rows = "\n".join(f"| M{index} | {index} |" for index in range(5))
    table = block(
        "table",
        BlockKind.TABLE,
        f"| Method | Score |\n| --- | --- |\n{rows}",
        1,
        page_no=3,
    )

    drafts = ChunkService(db_session, max_tokens=100, max_table_rows=2).build_drafts(
        [caption, table]
    )

    assert len(drafts) == 3
    assert [draft.source_text.count("| --- | --- |") for draft in drafts] == [1, 1, 1]
    assert [draft.structure_metadata["groupIndex"] for draft in drafts] == [0, 1, 2]
    assert all(draft.structure_metadata["groupCount"] == 3 for draft in drafts)
    assert len({draft.structure_metadata["tableGroupId"] for draft in drafts}) == 1
    assert drafts[0].source_text.startswith("Table 2. Metrics\n\n")
    assert drafts[1].source_text.startswith("Table 2. Metrics (continued)\n\n")
    assert drafts[1].structure_metadata["syntheticRepeat"] is True
    assert [
        len(re.findall(r"^\| M\d+ ", draft.source_text, re.MULTILINE))
        for draft in drafts
    ] == [2, 2, 1]


def test_docling_caption_reference_associates_non_adjacent_table(
    db_session: Session,
) -> None:
    caption = block(
        "caption",
        BlockKind.CAPTION,
        "Table 3. Ablation",
        0,
        metadata={"docling_self_ref": "#/texts/4"},
    )
    paragraph = block("paragraph", BlockKind.PARAGRAPH, "Lead-in text.", 1)
    table = block(
        "table",
        BlockKind.TABLE,
        "| Variant | Score |\n| --- | --- |\n| Base | 1.0 |",
        2,
        metadata={"docling_caption_refs": ["#/texts/4"]},
    )

    drafts = ChunkService(db_session, max_tokens=100).build_drafts(
        [caption, paragraph, table]
    )

    assert len(drafts) == 2
    assert drafts[0].source_text == "Lead-in text."
    assert drafts[1].source_text.startswith("Table 3. Ablation\n\n")
    assert drafts[1].source_block_ids == ["caption", "table"]


def test_referenced_caption_after_table_is_not_duplicated(db_session: Session) -> None:
    table = block(
        "table",
        BlockKind.TABLE,
        "| Variant | Score |\n| --- | --- |\n| Base | 1.0 |",
        0,
        metadata={"docling_caption_refs": ["#/texts/9"]},
    )
    caption = block(
        "caption",
        BlockKind.CAPTION,
        "Table 4. Late caption",
        1,
        metadata={"docling_self_ref": "#/texts/9"},
    )

    drafts = ChunkService(db_session, max_tokens=100).build_drafts([table, caption])

    assert len(drafts) == 1
    assert drafts[0].source_text.count("Table 4. Late caption") == 1
    assert drafts[0].source_block_ids == ["caption", "table"]


def test_markdown_parser_to_persisted_chunks_integration(
    db_session: Session, tmp_path
) -> None:
    source = tmp_path / "paper.md"
    source.write_text(
        "# Paper\n\nAbstract body.\n\n"
        "## Results\n\nTable 1. Scores\n\n"
        "| Method | Score |\n| --- | --- |\n| A | 0.9 |",
        encoding="utf-8",
    )
    blocks = ParserService().parse(source)
    job = add_job(db_session, "job_integration")

    chunks = ChunkService(db_session, max_tokens=100).create_chunks(job.job_id, blocks)

    assert [chunk.section_title for chunk in chunks] == ["Paper", "Results", "Results"]
    assert chunks[-1].chunk_type == ChunkType.TABLE.value
    assert chunks[-1].has_risk is True
    metadata = chunks[-1].structure_metadata
    assert metadata["originalTableBlockId"] in chunks[-1].source_block_ids
    assert len(list(db_session.scalars(select(RiskItem)))) == 1


def test_create_chunks_is_idempotent_and_inherits_risks(db_session: Session) -> None:
    job = add_job(db_session)
    risk = BlockRisk(risk_type=RiskType.STRUCTURE, message="双栏顺序已修正")
    blocks = [
        block("title", BlockKind.TITLE, "# Paper", 0),
        block("body", BlockKind.PARAGRAPH, "Body text.", 1, page_no=2, risks=[risk]),
    ]
    service = ChunkService(db_session, max_tokens=100)

    first = service.create_chunks(job.job_id, blocks)
    first_ids = [chunk.chunk_id for chunk in first]
    second = service.create_chunks(job.job_id, blocks)

    assert [chunk.chunk_id for chunk in second] == first_ids
    assert len(list(db_session.scalars(select(DocumentChunk)))) == 1
    risks = list(db_session.scalars(select(RiskItem)))
    assert len(risks) == 1
    assert risks[0].risk_type == RiskType.STRUCTURE.value
    risk_metadata = risks[0].metadata_json
    assert risk_metadata["sourceBlockIds"] == ["title", "body"]
    assert risk_metadata["pages"] == [2]
    assert risk_metadata["blockLocations"][0]["blockId"] == "body"
    chunk_metadata = second[0].structure_metadata
    assert chunk_metadata["blockKinds"] == ["title", "paragraph"]
    db_session.refresh(job)
    assert job.status == JobStatus.PARSED.value
    assert job.current_stage == "split_sections"
    assert job.total_chunks == 1


def test_rebuild_removes_stale_pending_chunk_risks(db_session: Session) -> None:
    job = add_job(db_session, "job_shrink")
    risk = BlockRisk(risk_type=RiskType.STRUCTURE, message="需要复核")
    initial = [
        block("h1", BlockKind.HEADING, "## One", 0),
        block("p1", BlockKind.PARAGRAPH, "First.", 1, risks=[risk]),
        block("h2", BlockKind.HEADING, "## Two", 2),
        block("p2", BlockKind.PARAGRAPH, "Second.", 3, risks=[risk]),
    ]
    service = ChunkService(db_session, max_tokens=100)
    service.create_chunks(job.job_id, initial)
    assert len(list(db_session.scalars(select(RiskItem)))) == 2

    service.create_chunks(job.job_id, initial[:2])

    assert len(list(db_session.scalars(select(DocumentChunk)))) == 1
    risks = list(db_session.scalars(select(RiskItem)))
    assert len(risks) == 1
    assert risks[0].chunk_id is not None


def test_empty_document_and_invalid_thresholds_are_rejected(
    db_session: Session,
) -> None:
    with pytest.raises(ValueError):
        ChunkService(db_session, max_tokens=0)
    with pytest.raises(ValueError):
        ChunkService(db_session, max_table_rows=0)

    job = add_job(db_session, "job_empty")
    with pytest.raises(AppError) as caught:
        ChunkService(db_session).create_chunks(job.job_id, [])
    assert caught.value.code == ErrorCode.VALIDATION_ERROR
    db_session.refresh(job)
    assert job.status == JobStatus.UPLOADED.value


def test_rebuild_rejects_non_pending_chunks(db_session: Session) -> None:
    job = add_job(db_session, "job_started")
    blocks = [block("body", BlockKind.PARAGRAPH, "Body text.", 0)]
    service = ChunkService(db_session, max_tokens=100)
    chunks = service.create_chunks(job.job_id, blocks)
    chunks[0].status = ChunkStatus.COMPLETED.value
    db_session.commit()

    with pytest.raises(AppError) as caught:
        service.create_chunks(job.job_id, blocks)

    assert caught.value.code == ErrorCode.INVALID_STATE
    assert (
        db_session.get(DocumentChunk, chunks[0].chunk_id).status
        == ChunkStatus.COMPLETED.value
    )


def test_create_chunks_rejects_missing_or_invalid_job_state(
    db_session: Session,
) -> None:
    service = ChunkService(db_session)
    blocks = [block("body", BlockKind.PARAGRAPH, "Body text.", 0)]

    with pytest.raises(AppError) as missing:
        service.create_chunks("job_missing", blocks)
    assert missing.value.code == ErrorCode.JOB_NOT_FOUND

    job = add_job(db_session, "job_translating")
    job.status = JobStatus.TRANSLATING.value
    db_session.commit()
    with pytest.raises(AppError) as invalid:
        service.create_chunks(job.job_id, blocks)
    assert invalid.value.code == ErrorCode.INVALID_STATE
