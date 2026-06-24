from collections import defaultdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.response import success
from app.db.session import get_db
from app.models.document_chunk import DocumentChunk
from app.models.risk_item import RiskItem
from app.models.translation_job import TranslationJob
from app.schemas.chunk_response import ChunkResponse

router = APIRouter(prefix="/api/jobs/{job_id}/chunks", tags=["chunks"])


@router.get("")
def list_chunks(
    job_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    if db.get(TranslationJob, job_id) is None:
        raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
    chunks = list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.job_id == job_id)
            .order_by(DocumentChunk.chunk_index)
        )
    )
    risk_types: dict[str, list[str]] = defaultdict(list)
    for risk in db.scalars(select(RiskItem).where(RiskItem.job_id == job_id)):
        if risk.chunk_id and risk.risk_type not in risk_types[risk.chunk_id]:
            risk_types[risk.chunk_id].append(risk.risk_type)
    return success(
        [
            ChunkResponse.model_validate(
                {
                    "chunk_id": chunk.chunk_id,
                    "chunk_index": chunk.chunk_index,
                    "section_title": chunk.section_title,
                    "section_path": chunk.section_path,
                    "chunk_type": chunk.chunk_type,
                    "status": chunk.status,
                    "has_risk": chunk.has_risk,
                    "risk_types": risk_types[chunk.chunk_id],
                    "risk_summary": chunk.risk_summary,
                    "source_preview": chunk.source_text[:120],
                    "translated_preview": (
                        chunk.translated_text[:120] if chunk.translated_text else None
                    ),
                    "boundary_reason": chunk.boundary_reason,
                    "boundary_score": chunk.boundary_score,
                    "semantic_topic": chunk.semantic_topic,
                    "translated_at": chunk.translated_at,
                }
            ).model_dump(by_alias=True, mode="json")
            for chunk in chunks
        ]
    )
