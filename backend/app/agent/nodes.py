from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.types import interrupt
from sqlalchemy import func, select

from app.agent.state import TranslationState
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.db.session import SessionLocal
from app.models.document_chunk import DocumentChunk
from app.models.enums import ChunkStatus, JobStatus
from app.models.translation_job import TranslationJob
from app.services.checkpoint_service import CheckpointService
from app.services.chunk_service import ChunkService
from app.services.document_ir_service import DocumentIRService
from app.services.output_service import OutputService
from app.services.parser_service import ParserService
from app.services.term_service import TermService
from app.services.translation_service import TranslationService
from app.storage.paths import get_storage_paths


class WorkflowNodes:
    def parse_document(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            self._assert_version(job)
            if job.document_ir_path and Path(job.document_ir_path).is_file():
                return {"workflow_version": job.workflow_version}
            now = datetime.now(timezone.utc)
            job.current_stage = "parse_document"
            job.started_at = job.started_at or now
            job.updated_at = now
            db.commit()

            paths = get_storage_paths()
            source = Path(job.original_file_path)
            blocks = ParserService().parse_to_markdown(
                source,
                paths.parsed_markdown(job.job_id),
                ocr_mode=job.ocr_mode,
                assets_dir=paths.parsed_assets_dir(job.job_id),
            )
            ir_service = DocumentIRService()
            document = ir_service.build(
                job.job_id,
                job.original_filename,
                blocks,
                paths.parsed_assets_dir(job.job_id),
            )
            ir_service.write(document, paths.document_ir(job.job_id))
            job.parsed_markdown_path = str(paths.parsed_markdown(job.job_id))
            job.document_ir_path = str(paths.document_ir(job.job_id))
            job.document_ir_version = document.version
            job.updated_at = datetime.now(timezone.utc)
            CheckpointService(db).save(
                job.job_id,
                "parse_document",
                {"documentIrPath": job.document_ir_path},
            )
            db.commit()
            return {"workflow_version": job.workflow_version}

    def split_sections(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            job.current_stage = "split_sections"
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
            if not job.document_ir_path:
                raise AppError(
                    ErrorCode.INVALID_STATE,
                    "任务缺少 DocumentIR",
                    status_code=409,
                )
            ir_service = DocumentIRService()
            document = ir_service.read(Path(job.document_ir_path))
            chunks = ChunkService(db).create_chunks(
                job.job_id, ir_service.to_parsed_blocks(document)
            )
            CheckpointService(db).save(
                job.job_id,
                "split_sections",
                {"totalChunks": len(chunks)},
            )
            db.commit()
            return {"current_chunk_index": None, "previous_summary": None}

    def extract_terms(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            job.current_stage = "extract_terms"
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
            texts = list(
                db.scalars(
                    select(DocumentChunk.source_text)
                    .where(DocumentChunk.job_id == job.job_id)
                    .order_by(DocumentChunk.chunk_index)
                )
            )
            terms = TermService(db).extract(job.job_id, texts)
            CheckpointService(db).save(
                job.job_id,
                "extract_terms",
                {"termCount": len(terms)},
            )
            db.commit()
            return {}

    def interrupt_for_term_review(
        self, state: TranslationState
    ) -> dict[str, Any]:
        with SessionLocal() as db:
            count = db.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.job_id == state["job_id"])
            )
        review_result = interrupt(
            {
                "jobId": state["job_id"],
                "message": "请确认术语表后继续",
                "chunkCount": count or 0,
            }
        )
        return {"review_result": review_result}

    def translate_chunk(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            if job.status == JobStatus.CANCELLED.value:
                return {"cancelled": True, "translation_done": True}
            if job.status != JobStatus.TRANSLATING.value:
                raise AppError(
                    ErrorCode.INVALID_STATE,
                    f"任务状态 {job.status} 不允许翻译",
                    status_code=409,
                )
            job.current_stage = "translate_chunk"
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
            service = TranslationService(db)
            chunk = service.next_pending(job.job_id)
            if chunk is None:
                return {"translation_done": True}
            translated = service.translate(
                job.job_id, chunk, state.get("previous_summary")
            )
            completed = db.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(
                    DocumentChunk.job_id == job.job_id,
                    DocumentChunk.status == ChunkStatus.COMPLETED.value,
                )
            ) or 0
            job.completed_chunks = completed
            job.progress_percent = (
                completed / job.total_chunks * 100 if job.total_chunks else 0
            )
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {
                "current_chunk_id": translated.chunk_id,
                "current_chunk_index": translated.chunk_index,
                "translation_done": False,
            }

    def summarize_chunk_context(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            job.current_stage = "summarize_chunk_context"
            chunk = db.get(DocumentChunk, state["current_chunk_id"])
            if chunk is None:
                raise AppError(ErrorCode.INVALID_STATE, "当前 chunk 不存在", status_code=409)
            summary = TranslationService(db).summarize(job.job_id, chunk)
            return {"previous_summary": summary}

    def mark_risks(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            job.current_stage = "mark_risks"
            chunk = db.get(DocumentChunk, state["current_chunk_id"])
            if chunk is None:
                raise AppError(ErrorCode.INVALID_STATE, "当前 chunk 不存在", status_code=409)
            TranslationService(db).mark_quality_risks(job.job_id, chunk)
            return {}

    def save_checkpoint(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            CheckpointService(db).save(
                state["job_id"],
                "chunk_completed",
                {
                    "currentChunkId": state.get("current_chunk_id"),
                    "previousSummary": state.get("previous_summary"),
                },
                state.get("current_chunk_index"),
            )
            db.commit()
        return {}

    def generate_outputs(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            job.current_stage = "generate_outputs"
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
            OutputService(db, get_storage_paths()).generate_documents(job.job_id)
            CheckpointService(db).save(job.job_id, "generate_outputs", {})
            db.commit()
        return {}

    def generate_report(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            job.current_stage = "generate_report"
            job.updated_at = datetime.now(timezone.utc)
            service = OutputService(db, get_storage_paths())
            now = datetime.now(timezone.utc)
            job.status = JobStatus.COMPLETED.value
            job.current_stage = "completed"
            job.completed_chunks = job.total_chunks
            job.progress_percent = 100
            job.completed_at = now
            job.updated_at = now
            service.generate_report(job.job_id)
            service.generate_manifest_and_package(job.job_id)
            CheckpointService(db).save(job.job_id, "generate_report", {"completed": True})
            db.commit()
        return {}

    @staticmethod
    def route_after_translation(state: TranslationState) -> str:
        if state.get("cancelled"):
            return "cancelled"
        return "outputs" if state.get("translation_done") else "summarize"

    @staticmethod
    def _job(db: Any, job_id: str) -> TranslationJob:
        job = db.get(TranslationJob, job_id)
        if job is None:
            raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
        return job

    @staticmethod
    def _assert_version(job: TranslationJob) -> None:
        current = get_settings().workflow_version
        if job.workflow_version != current:
            raise AppError(
                ErrorCode.INVALID_STATE,
                f"任务工作流版本 {job.workflow_version} 与当前版本 {current} 不兼容",
                status_code=409,
            )
