import re
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.models.document_chunk import DocumentChunk
from app.models.enums import ChunkStatus, RiskType
from app.models.risk_item import RiskItem
from app.services.llm_service import LLMService
from app.services.metric_service import MetricService
from app.services.term_service import TermService
from app.services.budget_service import BudgetService

NUMBER_PATTERN = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)*(?:%|[a-zA-Z]+)?")
FORMULA_PATTERN = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$", re.DOTALL)
CITATION_PATTERN = re.compile(r"\[\d+(?:\s*[-,]\s*\d+)*\]")


class TranslationService:
    def __init__(
        self,
        db: Session,
        llm: LLMService | None = None,
    ) -> None:
        self.db = db
        self.llm = llm

    def next_pending(self, job_id: str) -> DocumentChunk | None:
        return self.db.scalar(
            select(DocumentChunk)
            .where(
                DocumentChunk.job_id == job_id,
                DocumentChunk.status.in_(
                    [ChunkStatus.PENDING.value, ChunkStatus.FAILED.value]
                ),
            )
            .order_by(DocumentChunk.chunk_index)
            .limit(1)
        )

    def translate(
        self,
        job_id: str,
        chunk: DocumentChunk,
        previous_summary: str | None,
    ) -> DocumentChunk:
        llm = self.llm or LLMService()
        chunk.status = ChunkStatus.TRANSLATING.value
        chunk.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        try:
            BudgetService(self.db).assert_available(job_id)
            result = llm.translate_chunk(
                chunk.source_text,
                TermService(self.db).confirmed_map(job_id),
                self._section_summary(job_id, chunk),
                previous_summary,
            )
            chunk.translated_text = result.content
            chunk.status = ChunkStatus.COMPLETED.value
            chunk.translated_at = datetime.now(timezone.utc)
            chunk.updated_at = chunk.translated_at
            MetricService(self.db).record(
                job_id,
                result,
                chunk_id=chunk.chunk_id,
                model=llm.settings.llm_model,
            )
            self.db.commit()
            self.db.refresh(chunk)
            return chunk
        except Exception:
            self.db.rollback()
            chunk = self.db.get(DocumentChunk, chunk.chunk_id)
            if chunk:
                chunk.status = ChunkStatus.FAILED.value
                chunk.updated_at = datetime.now(timezone.utc)
                self.db.commit()
            raise

    def summarize(self, job_id: str, chunk: DocumentChunk) -> str:
        if not chunk.translated_text:
            raise AppError(
                ErrorCode.INVALID_STATE,
                "chunk 尚未翻译，不能生成上下文摘要",
                status_code=409,
            )
        llm = self.llm or LLMService()
        BudgetService(self.db).assert_available(job_id)
        result = llm.summarize_chunk(chunk.source_text, chunk.translated_text)
        chunk.context_summary = result.content
        chunk.updated_at = datetime.now(timezone.utc)
        MetricService(self.db).record(
            job_id,
            result,
            chunk_id=chunk.chunk_id,
            model=llm.settings.llm_model,
        )
        self.db.commit()
        return result.content

    def mark_quality_risks(self, job_id: str, chunk: DocumentChunk) -> list[RiskItem]:
        if not chunk.translated_text:
            return []
        findings = self._deterministic_findings(
            chunk.source_text, chunk.translated_text
        )
        llm = self.llm or LLMService()
        BudgetService(self.db).assert_available(job_id)
        quality, result = llm.check_quality(chunk.source_text, chunk.translated_text)
        MetricService(self.db).record(
            job_id,
            result,
            chunk_id=chunk.chunk_id,
            model=llm.settings.llm_model,
        )
        findings.extend(
            (self._risk_type(issue.type), issue.message, issue.severity)
            for issue in quality.issues
        )
        now = datetime.now(timezone.utc)
        risks: list[RiskItem] = []
        existing = {
            (risk.risk_type, risk.message)
            for risk in self.db.scalars(
                select(RiskItem).where(RiskItem.chunk_id == chunk.chunk_id)
            )
        }
        for risk_type, message, severity in findings:
            if (risk_type.value, message) in existing:
                continue
            risk = RiskItem(
                risk_id=self._stable_risk_id(chunk.chunk_id, risk_type.value, message),
                job_id=job_id,
                chunk_id=chunk.chunk_id,
                risk_type=risk_type.value,
                severity=severity,
                message=message,
                source_excerpt=chunk.source_text[:500],
                metadata_json={"qualityCheck": True},
                created_at=now,
            )
            self.db.add(risk)
            risks.append(risk)
        if risks:
            chunk.has_risk = True
            chunk.risk_summary = "；".join(
                dict.fromkeys(
                    filter(
                        None,
                        [
                            chunk.risk_summary,
                            *(risk.message for risk in risks),
                        ],
                    )
                )
            )
        self.db.commit()
        return risks

    def _section_summary(
        self, job_id: str, chunk: DocumentChunk
    ) -> str | None:
        summaries = list(
            self.db.scalars(
                select(DocumentChunk.context_summary)
                .where(
                    DocumentChunk.job_id == job_id,
                    DocumentChunk.section_path == chunk.section_path,
                    DocumentChunk.chunk_index < chunk.chunk_index,
                    DocumentChunk.context_summary.is_not(None),
                )
                .order_by(DocumentChunk.chunk_index.desc())
                .limit(3)
            )
        )
        return "\n".join(reversed([summary for summary in summaries if summary])) or None

    @staticmethod
    def _deterministic_findings(
        source: str, translated: str
    ) -> list[tuple[RiskType, str, str]]:
        findings: list[tuple[RiskType, str, str]] = []
        for pattern, risk_type, label in (
            (NUMBER_PATTERN, RiskType.NUMBER_MISMATCH, "数字或单位"),
            (FORMULA_PATTERN, RiskType.FORMULA_MISMATCH, "公式"),
            (CITATION_PATTERN, RiskType.CITATION_MISMATCH, "引用"),
        ):
            source_values = pattern.findall(source)
            translated_values = pattern.findall(translated)
            if source_values != translated_values:
                findings.append(
                    (
                        risk_type,
                        f"{label}序列与原文不一致，建议人工复核",
                        "HIGH",
                    )
                )
        return findings

    @staticmethod
    def _risk_type(value: str) -> RiskType:
        normalized = value.upper()
        aliases = {
            "OMISSION": RiskType.OMISSION,
            "TERMINOLOGY": RiskType.TERMINOLOGY,
            "NUMBER": RiskType.NUMBER_MISMATCH,
            "NUMBER_MISMATCH": RiskType.NUMBER_MISMATCH,
            "FORMULA": RiskType.FORMULA_MISMATCH,
            "FORMULA_MISMATCH": RiskType.FORMULA_MISMATCH,
            "CITATION": RiskType.CITATION_MISMATCH,
            "CITATION_MISMATCH": RiskType.CITATION_MISMATCH,
        }
        return aliases.get(normalized, RiskType.OMISSION)

    @staticmethod
    def _stable_risk_id(chunk_id: str, risk_type: str, message: str) -> str:
        return f"risk_{uuid5(NAMESPACE_URL, f'{chunk_id}:{risk_type}:{message}').hex}"
