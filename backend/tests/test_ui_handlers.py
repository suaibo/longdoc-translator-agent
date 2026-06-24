from pathlib import Path

from sqlalchemy.orm import Session

from app.storage.paths import StoragePaths
from app.ui import handlers


def test_gradio_handler_creates_and_reads_job(
    db_session: Session, tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "paper.md"
    source.write_text("# Paper\n\nBody.", encoding="utf-8")
    paths = StoragePaths(tmp_path / "storage")
    paths.ensure_root()

    monkeypatch.setattr(handlers, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(handlers, "get_storage_paths", lambda: paths)
    monkeypatch.setattr(
        handlers,
        "get_worker",
        lambda: type("Worker", (), {"enqueue": lambda self, job_id: None})(),
    )

    message, _dropdown, job_id = handlers.create_job(str(source), "paper")

    assert job_id is not None
    assert job_id in message
    result = handlers.refresh_dashboard(job_id)
    summary, terms, chunks, risks = result[:4]
    outputs = result[4:]
    assert "UPLOADED" in summary
    assert terms == []
    assert chunks == []
    assert risks == []
    assert all(output is None for output in outputs[:-1])
    assert outputs[-1] is not None
