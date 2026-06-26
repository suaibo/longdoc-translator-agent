import zipfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.translation_job import TranslationJob
from app.services.output_service import OutputService
from app.storage.paths import StoragePaths


def test_outputs_include_safe_html_manifest_source_and_package(
    db_session: Session, tmp_path: Path
) -> None:
    paths = StoragePaths(tmp_path / "storage")
    paths.ensure_root()
    source_dir = paths.upload_dir("job_output")
    source_dir.mkdir(parents=True)
    source = source_dir / "original.md"
    source.write_text("# Paper", encoding="utf-8")
    now = datetime.now(timezone.utc)
    db_session.add(
        TranslationJob(
            job_id="job_output",
            original_filename="../paper.md",
            original_file_path=str(source),
            mode="paper",
            status="TRANSLATING",
            current_stage="generate_outputs",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        DocumentChunk(
            chunk_id="chunk_output",
            job_id="job_output",
            chunk_index=0,
            section_title="Paper",
            chunk_type="TEXT",
            source_text='<script>alert("x")</script>',
            translated_text="中文译文",
            status="COMPLETED",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()
    service = OutputService(db_session, paths)

    service.generate_documents("job_output")
    service.generate_report("job_output")
    manifest, package = service.generate_manifest_and_package("job_output")

    html_text = paths.output_file("job_output", "bilingual_html").read_text(
        encoding="utf-8"
    )
    assert "<script>" not in html_text
    assert "&lt;script&gt;" in html_text
    assert manifest.is_file()
    replay = paths.replay_dataset("job_output").read_text(encoding="utf-8")
    assert '"recordType": "chunk"' in replay
    assert "sourceText" not in replay
    assert '<script>alert("x")</script>' not in replay
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        assert "source/paper.md" in names
        assert "replay.jsonl" in names
        assert not any(".." in Path(name).parts for name in names)


def test_translated_html_preserves_author_table_and_formula_asset(
    db_session: Session, tmp_path: Path
) -> None:
    paths = StoragePaths(tmp_path / "storage")
    paths.ensure_root()
    source_dir = paths.upload_dir("job_assets")
    source_dir.mkdir(parents=True)
    source = source_dir / "original.pdf"
    source.write_bytes(b"%PDF-test")
    assets_dir = paths.parsed_assets_dir("job_assets")
    formula_asset = assets_dir / "formulas" / "formula.png"
    formula_asset.parent.mkdir(parents=True)
    formula_asset.write_bytes(b"png")
    figure_asset = assets_dir / "figures" / "figure.png"
    figure_asset.parent.mkdir(parents=True)
    figure_asset.write_bytes(b"png")
    document_ir = paths.document_ir("job_assets")
    document_ir.parent.mkdir(parents=True, exist_ok=True)
    document_ir.write_text(
        """
{
  "assets": [
    {
      "relativePath": "assets/formulas/formula.png",
      "metadata": {"blockId": "formula_block"}
    },
    {
      "relativePath": "assets/figures/figure.png",
      "metadata": {"blockId": "figure_block"}
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    now = datetime.now(timezone.utc)
    db_session.add(
        TranslationJob(
            job_id="job_assets",
            original_filename="paper.pdf",
            original_file_path=str(source),
            document_ir_path=str(document_ir),
            mode="paper",
            status="TRANSLATING",
            current_stage="generate_outputs",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add_all(
        [
            DocumentChunk(
                chunk_id="author_chunk",
                job_id="job_assets",
                chunk_index=0,
                section_title="Paper",
                chunk_type="TABLE",
                source_text=(
                    "| Ashish Vaswani Google Brain avaswani@google.com | "
                    "Noam Shazeer Google Brain noam@google.com |\n"
                    "| --- | --- |"
                ),
                translated_text=(
                    "| Ashish Vaswani 谷歌大脑 avaswani@google.com | "
                    "Noam Shazeer 谷歌大脑 noam@google.com |\n"
                    "| --- | --- |"
                ),
                status="COMPLETED",
                created_at=now,
                updated_at=now,
            ),
            DocumentChunk(
                chunk_id="formula_chunk",
                job_id="job_assets",
                chunk_index=1,
                section_title="Math",
                chunk_type="FORMULA",
                source_text="$$\n\n$$",
                source_block_ids=["formula_block"],
                translated_text=r"\n\n",
                status="COMPLETED",
                created_at=now,
                updated_at=now,
            ),
            DocumentChunk(
                chunk_id="figure_chunk",
                job_id="job_assets",
                chunk_index=2,
                section_title="Figure",
                chunk_type="PICTURE",
                source_text="Figure 1: Model architecture.",
                source_block_ids=["figure_block"],
                translated_text="图1：模型架构。",
                status="COMPLETED",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()

    OutputService(db_session, paths).generate_documents("job_assets")

    html_text = paths.output_file("job_assets", "translated_html").read_text(
        encoding="utf-8"
    )
    assert "谷歌大脑" not in html_text
    assert "Google Brain" in html_text
    assert '<div class="author-card">' in html_text
    assert 'src="assets/formulas/formula.png"' in html_text
    assert 'src="assets/figures/figure.png"' in html_text
    assert r"\n\n" not in html_text
