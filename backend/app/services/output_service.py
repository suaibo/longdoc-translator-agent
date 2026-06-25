import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.models.document_chunk import DocumentChunk
from app.models.risk_item import RiskItem
from app.models.term_entry import TermEntry
from app.models.translation_job import TranslationJob
from app.models.translation_metric import TranslationMetric
from app.models.enums import JobStatus
from app.services.render_service import RenderService
from app.services.replay_service import ReplayService
from app.storage.paths import StoragePaths

OUTPUT_TYPES = {
    "bilingual": ("bilingual.md", "text/markdown"),
    "translated": ("translated.md", "text/markdown"),
    "report": ("report.md", "text/markdown"),
    "bilingual_html": ("bilingual.html", "text/html"),
    "translated_html": ("translated.html", "text/html"),
    "package": ("result.zip", "application/zip"),
}


class OutputService:
    def __init__(
        self,
        db: Session,
        paths: StoragePaths,
        renderer: RenderService | None = None,
    ) -> None:
        self.db = db
        self.paths = paths
        self.renderer = renderer or RenderService()

    def generate_documents(self, job_id: str) -> dict[str, Path]:
        job = self._job(job_id)
        chunks = self._chunks(job_id)
        output_dir = self.paths.output_dir(job_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        bilingual_md = self._bilingual_markdown(job, chunks)
        translated_md = self._translated_markdown(chunks)
        bilingual_html = self._bilingual_html(job, chunks)
        translated_html = self._translated_html(job, chunks)
        outputs = {
            "bilingual": self.paths.output_file(job_id, "bilingual"),
            "translated": self.paths.output_file(job_id, "translated"),
            "bilingual_html": self.paths.output_file(job_id, "bilingual_html"),
            "translated_html": self.paths.output_file(job_id, "translated_html"),
        }
        self.renderer.write_text_atomic(outputs["bilingual"], bilingual_md)
        self.renderer.write_text_atomic(outputs["translated"], translated_md)
        self.renderer.write_text_atomic(outputs["bilingual_html"], bilingual_html)
        self.renderer.write_text_atomic(outputs["translated_html"], translated_html)
        return outputs

    def generate_report(self, job_id: str) -> Path:
        job = self._job(job_id)
        terms = list(
            self.db.scalars(
                select(TermEntry)
                .where(TermEntry.job_id == job_id)
                .order_by(TermEntry.source_term)
            )
        )
        risks = list(
            self.db.scalars(
                select(RiskItem)
                .where(RiskItem.job_id == job_id)
                .order_by(RiskItem.created_at)
            )
        )
        metrics = list(
            self.db.scalars(
                select(TranslationMetric).where(TranslationMetric.job_id == job_id)
            )
        )
        lines = [
            f"# {job.original_filename} 翻译报告",
            "",
            "## 任务",
            "",
            f"- 状态：{job.status}",
            f"- Chunk：{job.completed_chunks}/{job.total_chunks}",
            f"- 工作流版本：{job.workflow_version}",
            f"- Prompt 版本：{job.prompt_version}",
            "",
            "## 术语",
            "",
            "| 原文 | 译名 | 备注 |",
            "| --- | --- | --- |",
            *[
                f"| {self._md(term.source_term)} | "
                f"{self._md(term.confirmed_translation or term.suggested_translation)} | "
                f"{self._md(term.note or '')} |"
                for term in terms
            ],
            "",
            "## 风险",
            "",
            *(
                [
                    f"- **{risk.severity} / {risk.risk_type}**：{risk.message}"
                    for risk in risks
                ]
                or ["- 未记录风险项。"]
            ),
            "",
            "## 调用指标",
            "",
            f"- Prompt tokens：{sum(item.prompt_tokens for item in metrics)}",
            f"- Completion tokens：{sum(item.completion_tokens for item in metrics)}",
            f"- 总 tokens：{sum(item.total_tokens for item in metrics)}",
            f"- 总耗时：{sum(item.elapsed_ms for item in metrics)} ms",
            f"- 重试次数：{sum(item.retry_count for item in metrics)}",
            "",
        ]
        destination = self.paths.output_file(job_id, "report")
        self.renderer.write_text_atomic(destination, "\n".join(lines))
        return destination

    def generate_manifest_and_package(self, job_id: str) -> tuple[Path, Path]:
        job = self._job(job_id)
        output_dir = self.paths.output_dir(job_id)
        ReplayService(self.db).export(job_id, self.paths.replay_dataset(job_id))
        files: list[dict[str, Any]] = []
        for output_type, (filename, media_type) in OUTPUT_TYPES.items():
            if output_type == "package":
                continue
            path = output_dir / filename
            if path.is_file():
                files.append(
                    {
                        "type": output_type,
                        "path": filename,
                        "mediaType": media_type,
                        "sha256": self._sha256(path),
                    }
                )
        parsed_assets = self.paths.parsed_assets_dir(job_id)
        output_assets = output_dir / "assets"
        if parsed_assets.is_dir():
            if output_assets.exists():
                shutil.rmtree(output_assets)
            shutil.copytree(parsed_assets, output_assets)
            for asset in output_assets.rglob("*"):
                if asset.is_file():
                    files.append(
                        {
                            "type": "asset",
                            "path": asset.relative_to(output_dir).as_posix(),
                            "mediaType": "application/octet-stream",
                            "sha256": self._sha256(asset),
                        }
                    )
        source_path = Path(job.original_file_path)
        replay_path = self.paths.replay_dataset(job_id)
        files.append(
            {
                "type": "replay",
                "path": replay_path.name,
                "mediaType": "application/x-ndjson",
                "sha256": self._sha256(replay_path),
            }
        )
        manifest = {
            "version": "1",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "files": files,
            "source": {
                "filename": job.original_filename,
                "sha256": self._sha256(source_path),
            },
        }
        manifest_path = self.paths.output_manifest(job_id)
        self.renderer.write_text_atomic(
            manifest_path,
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
        package_path = self.paths.output_file(job_id, "package")
        temporary = package_path.with_suffix(".zip.tmp")
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in files:
                path = self._safe_output_path(output_dir, item["path"])
                archive.write(path, item["path"])
            archive.write(manifest_path, "manifest.json")
            archive.write(
                source_path, f"source/{self._safe_filename(job.original_filename)}"
            )
        temporary.replace(package_path)
        job.output_manifest_path = str(manifest_path)
        self.db.commit()
        return manifest_path, package_path

    def list_outputs(self, job_id: str) -> list[dict[str, Any]]:
        job = self._job(job_id)
        return [
            {
                "type": output_type,
                "filename": filename,
                "mediaType": media_type,
                "available": (
                    job.status == JobStatus.COMPLETED.value
                    and self.paths.output_file(job_id, output_type).is_file()
                ),
            }
            for output_type, (filename, media_type) in OUTPUT_TYPES.items()
        ]

    def get_output(self, job_id: str, output_type: str) -> Path:
        job = self._job(job_id)
        if job.status != JobStatus.COMPLETED.value:
            raise AppError(ErrorCode.INVALID_STATE, status_code=409)
        if output_type not in OUTPUT_TYPES:
            raise AppError(ErrorCode.OUTPUT_NOT_FOUND, status_code=404)
        path = self.paths.output_file(job_id, output_type)
        if not path.is_file():
            raise AppError(ErrorCode.OUTPUT_NOT_FOUND, status_code=404)
        return path

    def source_file(self, job_id: str) -> tuple[Path, str]:
        job = self._job(job_id)
        path = Path(job.original_file_path)
        if not path.is_file():
            raise AppError(ErrorCode.OUTPUT_NOT_FOUND, status_code=404)
        return path, self._safe_filename(job.original_filename)

    def _bilingual_markdown(
        self, job: TranslationJob, chunks: list[DocumentChunk]
    ) -> str:
        parts = ["# 双语对照", ""]
        for chunk in chunks:
            parts.extend(
                [
                    f"<!-- chunk:{chunk.chunk_id} -->",
                    "### Original",
                    self.renderer.markdown_chunk(chunk, translated=False),
                    "",
                    f"### 译文（{job.target_language.upper()}）",
                    self.renderer.markdown_chunk(chunk, translated=True),
                    "",
                ]
            )
        return "\n".join(parts).strip() + "\n"

    def _translated_markdown(self, chunks: list[DocumentChunk]) -> str:
        return (
            "\n\n".join(
                self.renderer.markdown_chunk(chunk, translated=True) for chunk in chunks
            ).strip()
            + "\n"
        )

    def _bilingual_html(self, job: TranslationJob, chunks: list[DocumentChunk]) -> str:
        body = "\n".join(
            '<section class="pair">'
            f'<div class="source">{self.renderer.html_chunk(chunk, False)}</div>'
            f'<div class="translation">{self.renderer.html_chunk(chunk, True)}</div>'
            "</section>"
            for chunk in chunks
        )
        return self.renderer.document_html(
            job.original_filename,
            body,
            bilingual=True,
            target_language=job.target_language,
        )

    def _translated_html(self, job: TranslationJob, chunks: list[DocumentChunk]) -> str:
        body = "\n".join(self.renderer.html_chunk(chunk, True) for chunk in chunks)
        return self.renderer.document_html(
            job.original_filename,
            body,
            bilingual=False,
            target_language=job.target_language,
        )

    def _job(self, job_id: str) -> TranslationJob:
        job = self.db.get(TranslationJob, job_id)
        if job is None:
            raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
        return job

    def _chunks(self, job_id: str) -> list[DocumentChunk]:
        return list(
            self.db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.job_id == job_id)
                .order_by(DocumentChunk.chunk_index)
            )
        )

    @staticmethod
    def _safe_output_path(root: Path, relative: str) -> Path:
        # Manifest paths are untrusted derived data. Resolve and contain them
        # before adding files to the downloadable archive.
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError(f"unsafe output path: {relative}")
        candidate = (root / relative).resolve()
        if root.resolve() not in candidate.parents:
            raise ValueError(f"output path escapes root: {relative}")
        return candidate

    @staticmethod
    def _safe_filename(filename: str) -> str:
        cleaned = Path(filename).name.replace("\x00", "")
        return cleaned or "source.bin"

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _md(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")
