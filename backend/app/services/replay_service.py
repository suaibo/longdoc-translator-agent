import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document_chunk import DocumentChunk
from app.models.risk_item import RiskItem
from app.models.translation_job import TranslationJob
from app.models.workflow_event import WorkflowEvent


class ReplayService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def export(self, job_id: str, destination: Path) -> Path:
        job = self.db.get(TranslationJob, job_id)
        if job is None:
            raise ValueError("job not found")
        risks_by_chunk: dict[str, list[str]] = {}
        for risk in self.db.scalars(
            select(RiskItem).where(RiskItem.job_id == job_id)
        ):
            if risk.chunk_id:
                risks_by_chunk.setdefault(risk.chunk_id, []).append(
                    risk.risk_type
                )
        records = [
            {
                "recordType": "job",
                "jobId": job_id,
                "mode": job.mode,
                "workflowVersion": job.workflow_version,
                "promptVersion": job.prompt_version,
                "status": job.status,
            }
        ]
        include_text = get_settings().replay_include_text
        for chunk in self.db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.job_id == job_id)
            .order_by(DocumentChunk.chunk_index)
        ):
            record = {
                "recordType": "chunk",
                "chunkIndex": chunk.chunk_index,
                "chunkType": chunk.chunk_type,
                "sectionPath": chunk.section_path,
                "status": chunk.status,
                "sourceSha256": self._hash(chunk.source_text),
                "translationSha256": self._hash(chunk.translated_text or ""),
                "sourceChars": len(chunk.source_text),
                "translationChars": len(chunk.translated_text or ""),
                "revisionCount": chunk.revision_count,
                "riskTypes": sorted(set(risks_by_chunk.get(chunk.chunk_id, []))),
            }
            if include_text:
                record["sourceText"] = chunk.source_text
                record["translatedText"] = chunk.translated_text
            records.append(record)
        for event in self.db.scalars(
            select(WorkflowEvent)
            .where(WorkflowEvent.job_id == job_id)
            .order_by(WorkflowEvent.created_at)
        ):
            records.append(
                {
                    "recordType": "event",
                    "node": event.node,
                    "status": event.status,
                    "elapsedMs": event.elapsed_ms,
                }
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in records)
            + "\n",
            encoding="utf-8",
        )
        return destination

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
