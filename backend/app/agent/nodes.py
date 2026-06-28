from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from uuid import uuid4
from typing import Any

from langgraph.types import interrupt
from sqlalchemy import func, select, text

from app.agent.state import TranslationState
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.db.session import SessionLocal
from app.models.document_chunk import DocumentChunk
from app.models.enums import (
    ChunkStatus,
    JobStatus,
    ReviewStatus,
    ReviewType,
    RiskType,
)
from app.models.risk_item import RiskItem
from app.models.translation_job import TranslationJob
from app.models.translation_metric import TranslationMetric
from app.services.boundary_analysis import BoundaryAnalysisService
from app.services.checkpoint_service import CheckpointService
from app.services.chunk_service import ChunkService
from app.services.document_ir_service import DocumentIRService
from app.services.event_service import EventService
from app.services.output_service import OutputService
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.metric_service import MetricService
from app.services.parser_service import ParserService
from app.services.pretranslation_service import PretranslationService
from app.services.review_service import ReviewService
from app.services.term_service import TermService
from app.services.translation_service import TranslationService
from app.storage.paths import get_storage_paths
from app.storage.object_store import ObjectStorageService


class WorkflowNodes:
    def parse_document_safe(self, state: TranslationState) -> dict[str, Any]:
        try:
            result = self.parse_document(state)
            return {**result, "parse_error": None}
        except Exception as exc:
            return {
                "parse_error": str(exc),
                "parse_retry_count": state.get("parse_retry_count", 0) + 1,
            }

    def fail_parse(self, state: TranslationState) -> dict[str, Any]:
        raise AppError(
            ErrorCode.DOCLING_PARSE_FAILED,
            state.get("parse_error") or "文档解析失败",
            status_code=500,
        )

    def detect_language(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            if not job.document_ir_path:
                raise AppError(
                    ErrorCode.INVALID_STATE,
                    "任务缺少 DocumentIR",
                    status_code=409,
                )
            service = DocumentIRService()
            document = service.read(Path(job.document_ir_path))
            language = BoundaryAnalysisService().detect_language(
                service.to_parsed_blocks(document)
            )
            job.source_language = language
            job.current_stage = "detect_language"
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {"source_language": language}

    def discover_boundary_candidates(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            service = DocumentIRService()
            document = service.read(Path(job.document_ir_path))
            candidates = BoundaryAnalysisService().discover(
                service.to_parsed_blocks(document)
            )
            job.current_stage = "discover_boundary_candidates"
            job.updated_at = datetime.now(timezone.utc)
            CheckpointService(db).save(
                job.job_id,
                "discover_boundary_candidates",
                {"candidateCount": len(candidates)},
            )
            db.commit()
            return {"boundary_candidates": candidates}

    def analyze_semantic_boundaries(self, state: TranslationState) -> dict[str, Any]:
        decisions: list[dict[str, Any]] = []
        try:
            with SessionLocal() as db:
                job = self._job(db, state["job_id"])
                job.current_stage = "analyze_semantic_boundaries"
                llm = LLMService()
                for candidate in state.get("boundary_candidates", []):
                    decision, result = llm.analyze_boundary(
                        candidate["left"],
                        candidate["right"],
                        candidate["signals"],
                        state.get("source_language") or "unknown",
                    )
                    MetricService(db).record(job.job_id, result)
                    item = {
                        **candidate,
                        "decision": decision.decision,
                        "confidence": decision.confidence,
                        "reason": decision.reason,
                        "sentenceComplete": decision.sentence_complete,
                    }
                    decisions.append(item)
                    if decision.decision == "UNCERTAIN":
                        self._add_boundary_risk(
                            db,
                            job.job_id,
                            RiskType.CROSS_PAGE_UNCERTAIN,
                            "跨页文本关系无法可靠判断，已按规则保守处理",
                            item,
                        )
                CheckpointService(db).save(
                    job.job_id,
                    "analyze_semantic_boundaries",
                    {"decisions": decisions},
                )
                db.commit()
            return {
                "boundary_decisions": decisions,
                "boundary_analysis_failed": False,
            }
        except Exception:
            return {
                "boundary_analysis_failed": True,
                "boundary_retry_count": state.get("boundary_retry_count", 0) + 1,
            }

    def fallback_boundary_analysis(self, state: TranslationState) -> dict[str, Any]:
        decisions = [
            {
                **candidate,
                "decision": "UNCERTAIN",
                "confidence": 0.0,
                "reason": "DeepSeek 边界判断失败，使用规则切分",
                "sentenceComplete": False,
            }
            for candidate in state.get("boundary_candidates", [])
        ]
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            for decision in decisions:
                self._add_boundary_risk(
                    db,
                    job.job_id,
                    RiskType.BOUNDARY_MODEL_FAILED,
                    "语义边界模型不可用，已回退到结构与 token 规则",
                    decision,
                )
            job.current_stage = "fallback_boundary_analysis"
            job.has_unresolved_risks = bool(decisions) or job.has_unresolved_risks
            db.commit()
        return {
            "boundary_decisions": decisions,
            "boundary_analysis_failed": False,
        }

    def normalize_cross_page_text(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            job.current_stage = "normalize_cross_page_text"
            job.updated_at = datetime.now(timezone.utc)
            CheckpointService(db).save(
                job.job_id,
                "normalize_cross_page_text",
                {"decisionCount": len(state.get("boundary_decisions", []))},
            )
            db.commit()
        return {}

    def validate_outputs(self, state: TranslationState) -> dict[str, Any]:
        paths = get_storage_paths()
        required = [
            paths.output_file(state["job_id"], name)
            for name in (
                "bilingual",
                "translated",
                "bilingual_html",
                "translated_html",
            )
        ]
        missing = [
            str(path)
            for path in required
            if not path.is_file() or path.stat().st_size == 0
        ]
        if missing:
            return {
                "output_valid": False,
                "output_error": f"输出缺失或为空: {', '.join(missing)}",
                "output_retry_count": state.get("output_retry_count", 0) + 1,
            }
        return {"output_valid": True, "output_error": None}

    def fail_output_validation(self, state: TranslationState) -> dict[str, Any]:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            state.get("output_error") or "输出完整性校验失败",
            status_code=500,
        )

    def parse_document(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            self._assert_version(job)
            if job.document_ir_path and Path(job.document_ir_path).is_file():
                job.status = JobStatus.PARSED.value
                job.current_stage = "parse_document"
                job.updated_at = datetime.now(timezone.utc)
                db.commit()
                return {"workflow_version": job.workflow_version}
            now = datetime.now(timezone.utc)
            job.current_stage = "parse_document"
            job.started_at = job.started_at or now
            job.updated_at = now
            db.commit()

            paths = get_storage_paths()
            source = Path(job.original_file_path)
            # A PostgreSQL advisory lock keeps memory-heavy PDF parsing at one
            # concurrent process across the whole deployment.
            parser_lock_key = 742001
            db.execute(text("SELECT pg_advisory_lock(:key)"), {"key": parser_lock_key})
            try:
                blocks = ParserService().parse_to_markdown(
                    source,
                    paths.parsed_markdown(job.job_id),
                    ocr_mode=job.ocr_mode,
                    assets_dir=paths.parsed_assets_dir(job.job_id),
                )
            finally:
                db.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": parser_lock_key},
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
            job.status = JobStatus.PARSED.value
            job.updated_at = datetime.now(timezone.utc)
            CheckpointService(db).save(
                job.job_id,
                "parse_document",
                {"documentIrPath": job.document_ir_path},
            )
            ObjectStorageService(paths).sync_parsed(job)
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
            decisions = {
                item["rightBlockId"]: item
                for item in state.get("boundary_decisions", [])
            }
            chunks = ChunkService(db, boundary_decisions=decisions).create_chunks(
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

    def interrupt_for_term_review(self, state: TranslationState) -> dict[str, Any]:
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

    def pretranslate_sample(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            if job.status == JobStatus.TRANSLATING.value and job.style_confirmed_at:
                return {}
            if job.status != JobStatus.WAITING_STYLE_REVIEW.value:
                raise AppError(
                    ErrorCode.INVALID_STATE,
                    f"任务状态 {job.status} 不允许生成预翻译",
                    status_code=409,
                )
            service = PretranslationService(db)
            preview = service.latest(job.job_id) or service.generate(job.job_id)
            EventService(db).record_job_event(
                job.job_id,
                "STYLE",
                "PREVIEWED",
                "预翻译样例已生成",
                {"previewId": preview.preview_id, "attemptNo": preview.attempt_no},
            )
            CheckpointService(db).save(
                job.job_id,
                "pretranslate_sample",
                {"previewId": preview.preview_id, "attemptNo": preview.attempt_no},
            )
            db.commit()
            return {"pretranslation_preview_id": preview.preview_id}

    def interrupt_for_style_review(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            if job.status == JobStatus.TRANSLATING.value and job.style_confirmed_at:
                return {"style_review_result": {"confirmed": True}}
            preview = PretranslationService(db).latest(job.job_id)
            preview_id = preview.preview_id if preview else None
        style_result = interrupt(
            {
                "jobId": state["job_id"],
                "previewId": preview_id,
                "message": "请确认预翻译风格后继续正式翻译",
            }
        )
        return {"style_review_result": style_result}

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
            completed = (
                db.scalar(
                    select(func.count())
                    .select_from(DocumentChunk)
                    .where(
                        DocumentChunk.job_id == job.job_id,
                        DocumentChunk.status == ChunkStatus.COMPLETED.value,
                    )
                )
                or 0
            )
            job.completed_chunks = completed
            job.progress_percent = (
                completed / job.total_chunks * 100 if job.total_chunks else 0
            )
            durations = list(
                db.scalars(
                    select(TranslationMetric.elapsed_ms).where(
                        TranslationMetric.job_id == job.job_id,
                        TranslationMetric.chunk_id.is_not(None),
                        TranslationMetric.elapsed_ms > 0,
                    )
                )
            )
            remaining = max(0, job.total_chunks - completed)
            job.eta_seconds = (
                0
                if remaining == 0
                else int(remaining * median(durations) / 1000) + 30
                if durations
                else None
            )
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
            EventService(db).record_job_event(
                job.job_id,
                "CHUNK",
                "COMPLETED",
                f"第 {translated.chunk_index + 1} 个片段已完成",
                {
                    "chunkId": translated.chunk_id,
                    "chunkIndex": translated.chunk_index,
                    "completedChunks": completed,
                    "totalChunks": job.total_chunks,
                    "progressPercent": job.progress_percent,
                    "etaSeconds": job.eta_seconds,
                },
            )
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
                raise AppError(
                    ErrorCode.INVALID_STATE, "当前 chunk 不存在", status_code=409
                )
            summary = TranslationService(db).summarize(job.job_id, chunk)
            return {"previous_summary": summary}

    def mark_risks(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            job.current_stage = "mark_risks"
            chunk = db.get(DocumentChunk, state["current_chunk_id"])
            if chunk is None:
                raise AppError(
                    ErrorCode.INVALID_STATE, "当前 chunk 不存在", status_code=409
                )
            risks = TranslationService(db).mark_quality_risks(job.job_id, chunk)
            high_risk = any(risk.severity == "HIGH" for risk in risks)
            if high_risk:
                job.has_unresolved_risks = True
                db.commit()
            return {"quality_has_high_risk": high_risk}

    def check_cross_chunk_coherence(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            chunk = db.get(DocumentChunk, state.get("current_chunk_id"))
            if chunk is None or chunk.chunk_index <= 0:
                return {
                    "quality_has_high_risk": state.get("quality_has_high_risk", False)
                }
            previous = db.scalar(
                select(DocumentChunk).where(
                    DocumentChunk.job_id == job.job_id,
                    DocumentChunk.chunk_index == chunk.chunk_index - 1,
                )
            )
            if previous is None:
                return {
                    "quality_has_high_risk": state.get("quality_has_high_risk", False)
                }
            left = previous.source_text.rstrip()
            right = chunk.source_text.lstrip()
            suspicious = bool(right[:1].islower()) or (
                left
                and left[-1] not in ".!?。！？；;؟؛])）】"
                and chunk.boundary_reason in {"TOKEN_HARD_LIMIT", "TOKEN_SOFT_LIMIT"}
            )
            if not suspicious:
                return {
                    "quality_has_high_risk": state.get("quality_has_high_risk", False)
                }
            candidate = {
                "leftBlockId": previous.chunk_id,
                "rightBlockId": chunk.chunk_id,
                "left": left[-800:],
                "right": right[:800],
                "signals": ["CROSS_CHUNK_SUSPICION"],
            }
            high_risk = state.get("quality_has_high_risk", False)
            try:
                decision, result = LLMService().analyze_boundary(
                    candidate["left"],
                    candidate["right"],
                    candidate["signals"],
                    job.source_language or "unknown",
                )
                MetricService(db).record(job.job_id, result, chunk_id=chunk.chunk_id)
                if decision.decision == "CONTINUE":
                    candidate.update(
                        {
                            "decision": decision.decision,
                            "confidence": decision.confidence,
                            "reason": decision.reason,
                        }
                    )
                    self._add_boundary_risk(
                        db,
                        job.job_id,
                        RiskType.SEMANTIC_DISCONTINUITY,
                        "当前 chunk 可能切断了上一句，建议对照原文复核",
                        candidate,
                        chunk_id=chunk.chunk_id,
                        severity="HIGH",
                    )
                    chunk.has_risk = True
                    job.has_unresolved_risks = True
                    high_risk = True
                db.commit()
            except Exception:
                self._add_boundary_risk(
                    db,
                    job.job_id,
                    RiskType.BOUNDARY_MODEL_FAILED,
                    "跨 chunk 连贯性检查失败，已保留译文并提示人工复核",
                    candidate,
                    chunk_id=chunk.chunk_id,
                )
                chunk.has_risk = True
                job.has_unresolved_risks = True
                db.commit()
            return {"quality_has_high_risk": high_risk}

    def update_long_term_memory(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            if job.mode != "novel":
                return {}
            chunk = db.get(DocumentChunk, state["current_chunk_id"])
            if chunk is None:
                raise AppError(
                    ErrorCode.INVALID_STATE, "当前 chunk 不存在", status_code=409
                )
            job.current_stage = "update_long_term_memory"
            MemoryService(db).update(job.job_id, chunk)
        return {}

    def interrupt_for_high_risk_review(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            if not job.require_high_risk_review:
                return {}
            chunk = db.get(DocumentChunk, state["current_chunk_id"])
            if chunk is None:
                raise AppError(
                    ErrorCode.INVALID_STATE, "当前 chunk 不存在", status_code=409
                )
            risks = list(
                db.scalars(
                    select(RiskItem).where(
                        RiskItem.chunk_id == chunk.chunk_id,
                        RiskItem.severity == "HIGH",
                    )
                )
            )
            if not risks:
                return {}
            review = ReviewService(db).get_or_create(
                job.job_id,
                ReviewType.HIGH_RISK_CHUNK,
                chunk.chunk_id,
                {
                    "chunkIndex": chunk.chunk_index,
                    "sectionPath": chunk.section_path,
                    "risks": [
                        {"type": risk.risk_type, "message": risk.message}
                        for risk in risks
                    ],
                },
            )
            if review.status == ReviewStatus.APPROVED.value:
                return {}
            self._wait_for_review(
                db,
                job,
                review.review_id,
                JobStatus.WAITING_RISK_REVIEW,
                "interrupt_for_high_risk_review",
            )
        return {"risk_review_result": {"approved": True}}

    def interrupt_for_chapter_review(self, state: TranslationState) -> dict[str, Any]:
        with SessionLocal() as db:
            job = self._job(db, state["job_id"])
            if not job.require_chapter_review:
                return {}
            chunk = db.get(DocumentChunk, state["current_chunk_id"])
            if chunk is None:
                raise AppError(
                    ErrorCode.INVALID_STATE, "当前 chunk 不存在", status_code=409
                )
            next_chunk = TranslationService(db).next_pending(job.job_id)
            if next_chunk and next_chunk.section_path == chunk.section_path:
                return {}
            section_path = chunk.section_path or [chunk.section_title or "未命名章节"]
            subject_id = "/".join(section_path)
            review = ReviewService(db).get_or_create(
                job.job_id,
                ReviewType.CHAPTER,
                subject_id,
                {
                    "sectionPath": section_path,
                    "lastChunkIndex": chunk.chunk_index,
                },
            )
            if review.status == ReviewStatus.APPROVED.value:
                return {}
            self._wait_for_review(
                db,
                job,
                review.review_id,
                JobStatus.WAITING_CHAPTER_REVIEW,
                "interrupt_for_chapter_review",
            )
        return {"chapter_review_result": {"approved": True}}

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
            job.eta_seconds = 0
            job.outputs_stale = False
            job.completed_at = now
            job.retention_expires_at = now + timedelta(
                days=get_settings().file_retention_days
            )
            job.updated_at = now
            service.generate_report(job.job_id)
            service.generate_manifest_and_package(job.job_id)
            ObjectStorageService(get_storage_paths()).sync_outputs(job)
            CheckpointService(db).save(
                job.job_id, "generate_report", {"completed": True}
            )
            db.commit()
        return {}

    @staticmethod
    def route_after_parse(state: TranslationState) -> str:
        if not state.get("parse_error"):
            return "success"
        return "retry" if state.get("parse_retry_count", 0) <= 2 else "failed"

    @staticmethod
    def route_boundary_analysis(state: TranslationState) -> str:
        return "analyze" if state.get("boundary_candidates") else "split"

    @staticmethod
    def route_after_boundary_analysis(state: TranslationState) -> str:
        if not state.get("boundary_analysis_failed"):
            return "normalize"
        return (
            "retry"
            if state.get("boundary_retry_count", 0)
            <= get_settings().boundary_llm_max_retries
            else "fallback"
        )

    @staticmethod
    def route_after_quality(state: TranslationState) -> str:
        if not state.get("quality_has_high_risk"):
            return "summarize"
        with SessionLocal() as db:
            job = db.get(TranslationJob, state["job_id"])
            return "review" if job and job.require_high_risk_review else "summarize"

    @staticmethod
    def route_after_output_validation(state: TranslationState) -> str:
        if state.get("output_valid"):
            return "report"
        return "retry" if state.get("output_retry_count", 0) <= 2 else "failed"

    @staticmethod
    def route_after_translation(state: TranslationState) -> str:
        if state.get("cancelled"):
            return "cancelled"
        return "outputs" if state.get("translation_done") else "summarize"

    @staticmethod
    def _add_boundary_risk(
        db: Any,
        job_id: str,
        risk_type: RiskType,
        message: str,
        decision: dict[str, Any],
        chunk_id: str | None = None,
        severity: str = "MEDIUM",
    ) -> None:
        db.add(
            RiskItem(
                risk_id=f"risk_{uuid4().hex}",
                job_id=job_id,
                chunk_id=chunk_id,
                risk_type=risk_type.value,
                severity=severity,
                message=message,
                source_excerpt=(
                    f"{decision.get('left', '')}\n--- PAGE ---\n"
                    f"{decision.get('right', '')}"
                )[:1000],
                metadata_json={
                    "leftBlockId": decision.get("leftBlockId"),
                    "rightBlockId": decision.get("rightBlockId"),
                    "leftPage": decision.get("leftPage"),
                    "rightPage": decision.get("rightPage"),
                    "decision": decision.get("decision"),
                    "reason": decision.get("reason"),
                    "systemAction": "保留原文并使用规则边界",
                    "suggestedAction": "对照原 PDF 检查跨页句子",
                },
                created_at=datetime.now(timezone.utc),
            )
        )

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

    @staticmethod
    def _wait_for_review(
        db: Any,
        job: TranslationJob,
        review_id: str,
        status: JobStatus,
        stage: str,
    ) -> None:
        job.status = status.value
        job.current_stage = stage
        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        interrupt(
            {
                "jobId": job.job_id,
                "reviewId": review_id,
                "reviewType": status.value,
                "message": "请在审核页确认后继续",
            }
        )
