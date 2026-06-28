from pathlib import Path

from sqlalchemy.orm import Session

from app.services.auth_service import AuthService
from app.storage.paths import StoragePaths
from app.ui import handlers


def test_gradio_handler_creates_and_reads_job(
    db_session: Session, tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "paper.md"
    source.write_text("# Paper\n\nBody.", encoding="utf-8")
    paths = StoragePaths(tmp_path / "storage")
    paths.ensure_root()
    _user, token = AuthService(db_session).register("ui-user", "test-password")

    monkeypatch.setattr(handlers, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(handlers, "get_storage_paths", lambda: paths)
    monkeypatch.setattr(
        handlers,
        "get_worker",
        lambda: type("Worker", (), {"enqueue": lambda self, job_id: None})(),
    )

    message, _dropdown, job_id = handlers.create_job(
        token, str(source), "paper", "auto", "zh"
    )

    assert job_id is not None
    assert "后台队列" in message
    result = handlers.refresh_dashboard(token, job_id)
    summary, terms, chunks, risks, events, reviews = result[:6]
    preview_and_editor_state = result[6:13]
    file_outputs = result[13:]
    assert "等待处理" in summary
    assert terms == []
    assert chunks == []
    assert risks == []
    assert events == []
    assert reviews == []
    assert preview_and_editor_state[0] == ""
    assert preview_and_editor_state[1] == ""
    assert preview_and_editor_state[2] == ""
    assert preview_and_editor_state[4] == ""
    assert preview_and_editor_state[5] == ""
    assert preview_and_editor_state[6] == []
    assert all(output is None for output in file_outputs[:-1])
    assert file_outputs[-1] is not None
