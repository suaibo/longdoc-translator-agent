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
    summary = result[0]
    stage_flow = result[1]
    panel_updates = result[2:8]
    terms, chunks, risks, events, reviews = result[8:13]
    preview_and_editor_state = result[13:20]
    file_outputs = result[20:27]
    detail_terms, detail_chunks, detail_risks, detail_reviews = result[27:31]
    assert "等待处理" in summary
    assert stage_flow["visible"] is True
    assert "stage-steps" in stage_flow["value"]
    assert [panel["visible"] for panel in panel_updates] == [
        False,
        True,
        False,
        False,
        False,
        False,
    ]
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
    assert detail_terms == []
    assert detail_chunks == []
    assert detail_risks == []
    assert detail_reviews == []
