from collections import defaultdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.models.document_chunk import DocumentChunk
from app.models.risk_item import RiskItem
from app.schemas.chunk_response import ChunkResponse
from app.schemas.job import to_camel
from app.services.chunk_edit_service import ChunkEditService
from app.services.event_service import EventService
from app.services.job_service import JobService
from app.storage.paths import get_storage_paths

router = APIRouter(prefix="/api/jobs/{job_id}/chunks", tags=["chunks"])


class ChunkTranslationUpdate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    translated_text: str
    edit_note: str | None = None


@router.get("")
def list_chunks(
    job_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
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
                    "source_text": None,
                    "translated_text": None,
                    "revision_count": chunk.revision_count,
                    "boundary_reason": chunk.boundary_reason,
                    "boundary_score": chunk.boundary_score,
                    "semantic_topic": chunk.semantic_topic,
                    "translated_at": chunk.translated_at,
                }
            ).model_dump(by_alias=True, mode="json")
            for chunk in chunks
        ]
    )


@router.get("/{chunk_id}")
def get_chunk(
    job_id: str,
    chunk_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
    chunk = _chunk(db, job_id, chunk_id)
    return success(_serialize_chunk(chunk, include_text=True))


@router.put("/{chunk_id}/translation")
def update_chunk_translation(
    job_id: str,
    chunk_id: str,
    request: ChunkTranslationUpdate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
    chunk = ChunkEditService(db).update_translation(
        job_id,
        chunk_id,
        user.user_id,
        request.translated_text,
        request.edit_note,
    )
    EventService(db).record_job_event(
        job_id,
        "EDIT",
        "SAVED",
        f"第 {chunk.chunk_index + 1} 个片段译文已保存",
        {"chunkId": chunk.chunk_id, "chunkIndex": chunk.chunk_index},
    )
    return success(_serialize_chunk(chunk, include_text=True))


@router.get("/{chunk_id}/versions")
def list_chunk_versions(
    job_id: str,
    chunk_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
    _chunk(db, job_id, chunk_id)
    versions = ChunkEditService(db).list_versions(job_id, chunk_id)
    return success(
        [
            {
                "versionId": version.version_id,
                "versionNo": version.version_no,
                "sourceType": version.source_type,
                "translatedText": version.translated_text,
                "editNote": version.edit_note,
                "createdByUserId": version.created_by_user_id,
                "model": version.model,
                "promptVersion": version.prompt_version,
                "createdAt": version.created_at.isoformat(),
            }
            for version in versions
        ]
    )


@router.post("/{chunk_id}/versions/{version_id}/restore")
def restore_chunk_version(
    job_id: str,
    chunk_id: str,
    version_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
    chunk = ChunkEditService(db).restore_version(
        job_id, chunk_id, version_id, user.user_id
    )
    EventService(db).record_job_event(
        job_id,
        "EDIT",
        "RESTORED",
        f"第 {chunk.chunk_index + 1} 个片段已恢复历史版本",
        {"chunkId": chunk.chunk_id, "versionId": version_id},
    )
    return success(_serialize_chunk(chunk, include_text=True))


def _chunk(db: Session, job_id: str, chunk_id: str) -> DocumentChunk:
    chunk = db.get(DocumentChunk, chunk_id)
    if chunk is None or chunk.job_id != job_id:
        from app.core.errors import AppError, ErrorCode

        raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
    return chunk


def _serialize_chunk(chunk: DocumentChunk, *, include_text: bool) -> dict[str, Any]:
    return ChunkResponse.model_validate(
        {
            "chunk_id": chunk.chunk_id,
            "chunk_index": chunk.chunk_index,
            "section_title": chunk.section_title,
            "section_path": chunk.section_path,
            "chunk_type": chunk.chunk_type,
            "status": chunk.status,
            "has_risk": chunk.has_risk,
            "risk_types": [risk.risk_type for risk in chunk.risks],
            "risk_summary": chunk.risk_summary,
            "source_preview": chunk.source_text[:120],
            "translated_preview": (
                chunk.translated_text[:120] if chunk.translated_text else None
            ),
            "source_text": chunk.source_text if include_text else None,
            "translated_text": chunk.translated_text if include_text else None,
            "revision_count": chunk.revision_count,
            "boundary_reason": chunk.boundary_reason,
            "boundary_score": chunk.boundary_score,
            "semantic_topic": chunk.semantic_topic,
            "translated_at": chunk.translated_at,
        }
    ).model_dump(by_alias=True, mode="json")
