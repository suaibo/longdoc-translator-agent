from pathlib import Path

import pytest

from app.storage.object_store import ObjectStorageService
from app.storage.paths import StoragePaths


def test_local_object_storage_uses_stable_user_job_keys(tmp_path: Path) -> None:
    storage = ObjectStorageService(StoragePaths(tmp_path / "storage"))

    assert storage.source_key("usr_1", "job_1", ".pdf") == (
        "usr_1/job_1/source/original.pdf"
    )
    assert storage.output_prefix("usr_1", "job_1") == "usr_1/job_1/outputs/"


def test_object_storage_rejects_path_traversal() -> None:
    with pytest.raises(ValueError):
        ObjectStorageService._validate_key("usr/job/../secret")
