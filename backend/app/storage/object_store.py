from __future__ import annotations

from pathlib import Path, PurePosixPath

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.storage.paths import StoragePaths, get_storage_paths


class ObjectStorageService:
    """Durable storage facade; local remains the development backend."""

    def __init__(self, paths: StoragePaths | None = None, client=None) -> None:
        self.settings = get_settings()
        self.paths = paths or get_storage_paths()
        self.backend = self.settings.storage_backend
        self.bucket = self.settings.s3_bucket
        self.client = client
        if self.backend == "s3" and self.client is None:
            if not self.bucket:
                raise RuntimeError("S3_BUCKET is required when STORAGE_BACKEND=s3")
            import boto3

            self.client = boto3.client(
                "s3",
                endpoint_url=self.settings.s3_endpoint_url or None,
                region_name=self.settings.s3_region or None,
                aws_access_key_id=self.settings.s3_access_key_id or None,
                aws_secret_access_key=self.settings.s3_secret_access_key or None,
            )

    def source_key(self, user_id: str, job_id: str, suffix: str) -> str:
        return self._key(user_id, job_id, "source", f"original{suffix.lower()}")

    def parsed_prefix(self, user_id: str, job_id: str) -> str:
        return self._key(user_id, job_id, "parsed") + "/"

    def output_prefix(self, user_id: str, job_id: str) -> str:
        return self._key(user_id, job_id, "outputs") + "/"

    def upload_file(
        self, local_path: Path, key: str, content_type: str | None = None
    ) -> None:
        self._validate_key(key)
        if self.backend == "local":
            return
        extra = {"ContentType": content_type} if content_type else None
        if extra:
            self.client.upload_file(str(local_path), self.bucket, key, ExtraArgs=extra)
        else:
            self.client.upload_file(str(local_path), self.bucket, key)

    def upload_tree(self, local_root: Path, prefix: str) -> None:
        if not local_root.is_dir() or self.backend == "local":
            return
        for path in local_root.rglob("*"):
            if path.is_file():
                relative = path.relative_to(local_root).as_posix()
                self.upload_file(path, f"{prefix.rstrip('/')}/{relative}")

    def download_file(self, key: str, destination: Path) -> Path:
        self._validate_key(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if self.backend == "local":
            if not destination.is_file():
                raise AppError(ErrorCode.OUTPUT_NOT_FOUND, status_code=404)
            return destination
        self.client.download_file(self.bucket, key, str(destination))
        return destination

    def download_tree(self, prefix: str, destination: Path) -> None:
        if self.backend == "local":
            return
        prefix = prefix.rstrip("/") + "/"
        self._validate_key(prefix)
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item["Key"]
                relative = PurePosixPath(key).relative_to(PurePosixPath(prefix))
                target = self._safe_destination(destination, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                self.client.download_file(self.bucket, key, str(target))

    def delete_prefix(self, prefix: str) -> None:
        if self.backend == "local":
            return
        prefix = prefix.rstrip("/") + "/"
        self._validate_key(prefix)
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": objects, "Quiet": True},
                )

    def presigned_download(self, key: str, filename: str) -> str | None:
        if self.backend == "local":
            return None
        self._validate_key(key)
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{Path(filename).name}"',
            },
            ExpiresIn=self.settings.s3_presign_seconds,
        )

    def materialize_job(self, job) -> None:
        if self.backend == "local":
            return
        source = Path(job.original_file_path)
        if not source.is_file() and job.source_storage_key:
            self.download_file(job.source_storage_key, source)
        self.download_tree(
            self.parsed_prefix(job.user_id, job.job_id),
            self.paths.parsed_dir(job.job_id),
        )
        self.download_tree(
            self.output_prefix(job.user_id, job.job_id),
            self.paths.output_dir(job.job_id),
        )

    def sync_parsed(self, job) -> None:
        self.upload_tree(
            self.paths.parsed_dir(job.job_id),
            self.parsed_prefix(job.user_id, job.job_id),
        )

    def sync_outputs(self, job) -> None:
        self.upload_tree(
            self.paths.output_dir(job.job_id),
            self.output_prefix(job.user_id, job.job_id),
        )

    @staticmethod
    def _key(*parts: str) -> str:
        cleaned = [str(PurePosixPath(part)).strip("/") for part in parts if part]
        key = "/".join(cleaned)
        ObjectStorageService._validate_key(key)
        return key

    @staticmethod
    def _validate_key(key: str) -> None:
        path = PurePosixPath(key)
        if path.is_absolute() or ".." in path.parts or not key.strip("/"):
            raise ValueError(f"unsafe storage key: {key}")

    @staticmethod
    def _safe_destination(root: Path, relative: PurePosixPath) -> Path:
        candidate = (root / Path(*relative.parts)).resolve()
        resolved_root = root.resolve()
        if candidate != resolved_root and resolved_root not in candidate.parents:
            raise ValueError("object key escapes destination")
        return candidate
