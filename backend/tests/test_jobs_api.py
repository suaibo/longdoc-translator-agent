from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import JobStatus
from app.models.translation_job import TranslationJob


def test_create_list_and_get_job(client: TestClient, db_session: Session) -> None:
    created = client.post(
        "/api/jobs",
        files={"file": ("../paper.md", b"# Abstract\n\nA paper.", "text/markdown")},
        data={"mode": "paper"},
    )

    assert created.status_code == 200
    job_id = created.json()["data"]["jobId"]
    job = db_session.get(TranslationJob, job_id)
    assert job is not None
    assert job.original_filename == "paper.md"
    assert Path(job.original_file_path).read_bytes() == b"# Abstract\n\nA paper."

    listed = client.get("/api/jobs")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["jobId"] == job_id
    assert listed.json()["data"][0]["status"] == "UPLOADED"

    detail = client.get(f"/api/jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["originalFilename"] == "paper.md"


def test_create_rejects_unsupported_type(client: TestClient) -> None:
    response = client.post("/api/jobs", files={"file": ("paper.docx", b"data")})

    assert response.status_code == 400
    assert response.json()["code"] == 40002


def test_create_rejects_file_over_limit(
    client: TestClient, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "4")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        response = client.post("/api/jobs", files={"file": ("paper.txt", b"12345")})
    finally:
        get_settings.cache_clear()

    assert response.status_code == 413
    assert response.json()["code"] == 40003
    uploads = tmp_path / "storage" / "uploads"
    assert not uploads.exists() or not any(uploads.iterdir())


def test_multiple_jobs_can_be_queued(client: TestClient) -> None:
    first = client.post("/api/jobs", files={"file": ("first.md", b"# First")})
    second = client.post("/api/jobs", files={"file": ("second.md", b"# Second")})

    assert first.status_code == 200
    assert second.status_code == 200


def test_missing_job_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/jobs/job_missing")

    assert response.status_code == 404
    assert response.json()["code"] == 40401


def test_create_accepts_novel_mode(client: TestClient) -> None:
    response = client.post(
        "/api/jobs",
        files={"file": ("novel.md", b"# Chapter 1\n\nAlice arrived.")},
        data={"mode": "novel"},
    )

    assert response.status_code == 200


def test_cancel_active_job_and_reject_second_cancel(client: TestClient) -> None:
    created = client.post("/api/jobs", files={"file": ("paper.txt", b"text")})
    job_id = created.json()["data"]["jobId"]

    cancelled = client.post(f"/api/jobs/{job_id}/cancel")
    repeated = client.post(f"/api/jobs/{job_id}/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["data"] == {"jobId": job_id, "status": "CANCELLED"}
    assert repeated.status_code == 409
    assert repeated.json()["code"] == 40901


def test_completed_job_cannot_be_cancelled(
    client: TestClient, db_session: Session
) -> None:
    created = client.post("/api/jobs", files={"file": ("paper.md", b"# Paper")})
    job_id = created.json()["data"]["jobId"]
    job = db_session.get(TranslationJob, job_id)
    assert job is not None
    job.status = JobStatus.COMPLETED.value
    db_session.commit()

    response = client.post(f"/api/jobs/{job_id}/cancel")

    assert response.status_code == 409
    assert response.json()["code"] == 40901
