from pathlib import Path

from app.core.config import PROJECT_ROOT, get_settings


def test_default_runtime_paths_are_anchored_to_project_root(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.storage_root == PROJECT_ROOT / "storage"
    assert settings.database_url.endswith("/storage/app.db")
