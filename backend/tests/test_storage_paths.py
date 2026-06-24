from pathlib import Path

import pytest

from app.storage.paths import StoragePaths


def test_storage_paths_follow_runtime_contract(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "storage")
    paths.ensure_root()

    assert paths.upload_dir("job_123") == tmp_path / "storage" / "uploads" / "job_123"
    assert paths.parsed_markdown("job_123") == (
        tmp_path / "storage" / "parsed" / "job_123" / "document.md"
    )
    assert paths.output_file("job_123", "bilingual") == (
        tmp_path / "storage" / "outputs" / "job_123" / "bilingual.md"
    )
    assert (tmp_path / "storage" / "uploads").is_dir()


def test_storage_paths_reject_path_traversal(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "storage")

    with pytest.raises(ValueError):
        paths.upload_dir("../outside")
    with pytest.raises(ValueError):
        paths.output_file("job_123", "unknown")
