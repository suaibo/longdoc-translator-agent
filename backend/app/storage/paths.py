from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings


@dataclass(frozen=True)
class StoragePaths:
    root: Path

    def ensure_root(self) -> None:
        for directory in ("uploads", "parsed", "outputs"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

    def upload_dir(self, job_id: str) -> Path:
        return self._job_dir("uploads", job_id)

    def parsed_dir(self, job_id: str) -> Path:
        return self._job_dir("parsed", job_id)

    def output_dir(self, job_id: str) -> Path:
        return self._job_dir("outputs", job_id)

    def parsed_markdown(self, job_id: str) -> Path:
        return self.parsed_dir(job_id) / "document.md"

    def document_ir(self, job_id: str) -> Path:
        return self.parsed_dir(job_id) / "document.ir.json"

    def parsed_assets_dir(self, job_id: str) -> Path:
        return self.parsed_dir(job_id) / "assets"

    def output_manifest(self, job_id: str) -> Path:
        return self.output_dir(job_id) / "manifest.json"

    def output_file(self, job_id: str, output_type: str) -> Path:
        filenames = {
            "bilingual": "bilingual.md",
            "translated": "translated.md",
            "report": "report.md",
            "bilingual_html": "bilingual.html",
            "translated_html": "translated.html",
            "package": "result.zip",
        }
        if output_type not in filenames:
            raise ValueError(f"unsupported output type: {output_type}")
        return self.output_dir(job_id) / filenames[output_type]

    def _job_dir(self, category: str, job_id: str) -> Path:
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        if not job_id or any(char not in allowed for char in job_id):
            raise ValueError("invalid job id")
        return self.root / category / job_id


def get_storage_paths() -> StoragePaths:
    paths = StoragePaths(get_settings().storage_root)
    paths.ensure_root()
    return paths
