from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.translation_job import TranslationJob
from app.services.retention_service import RetentionService
from app.storage.paths import StoragePaths


def test_retention_removes_expired_files_but_keeps_job(
    db_session: Session, tmp_path: Path
) -> None:
    paths = StoragePaths(tmp_path / "storage")
    paths.ensure_root()
    now = datetime.now(timezone.utc)
    job = TranslationJob(
        job_id="job_expired_files",
        original_filename="paper.md",
        original_file_path=str(paths.upload_dir("job_expired_files") / "original.md"),
        mode="paper",
        status="COMPLETED",
        current_stage="completed",
        retention_expires_at=now - timedelta(seconds=1),
        created_at=now,
        updated_at=now,
    )
    db_session.add(job)
    db_session.commit()
    paths.upload_dir(job.job_id).mkdir(parents=True)
    Path(job.original_file_path).write_text("source", encoding="utf-8")
    paths.output_dir(job.job_id).mkdir(parents=True)
    paths.output_file(job.job_id, "translated").write_text("result", encoding="utf-8")

    count = RetentionService(db_session, paths).cleanup_expired()

    assert count == 1
    assert db_session.get(TranslationJob, job.job_id) is not None
    assert not paths.upload_dir(job.job_id).exists()
    assert not paths.output_dir(job.job_id).exists()
