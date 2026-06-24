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
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        assert "source/paper.md" in names
        assert not any(".." in Path(name).parts for name in names)
