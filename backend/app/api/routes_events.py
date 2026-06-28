import asyncio
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.core.response import success
from app.db.session import SessionLocal
from app.db.session import get_db
from app.schemas.workflow_event import WorkflowEventResponse
from app.services.event_service import EventService
from app.services.job_service import JobService
from app.services.stream_token_service import StreamTokenService
from app.storage.paths import get_storage_paths

router = APIRouter(prefix="/api/jobs", tags=["events"])


@router.get("/{job_id}/events")
def list_events(
    job_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    after: int | None = None,
) -> dict[str, Any]:
    JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
    events = EventService(db).list_events(job_id, after_seq=after)
    data = [
        WorkflowEventResponse.model_validate(
            {
                "event_id": event.event_id,
                "event_seq": event.event_seq,
                "node": event.node,
                "event_type": event.event_type,
                "status": event.status,
                "message": event.message,
                "elapsed_ms": event.elapsed_ms,
                "metadata": event.metadata_json,
                "created_at": event.created_at,
            }
        ).model_dump(by_alias=True, mode="json")
        for event in events
    ]
    return success(data)


@router.post("/{job_id}/events/stream-token")
def issue_stream_token(
    job_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
    return success({"streamToken": StreamTokenService().issue(user.user_id, job_id)})


@router.get("/{job_id}/events/stream")
def stream_events(
    job_id: str,
    stream_token: Annotated[str, Query(alias="streamToken")],
    after: int | None = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
):
    payload = StreamTokenService().verify(stream_token, job_id)
    start_after = _last_seen(after, last_event_id)

    async def event_generator():
        last_seen = start_after
        while True:
            emitted = False
            with SessionLocal() as db:
                JobService(db, get_storage_paths()).get_job(job_id, payload["userId"])
                events = EventService(db).list_events(job_id, after_seq=last_seen)
                for event in events:
                    last_seen = event.event_seq
                    emitted = True
                    data = WorkflowEventResponse.model_validate(
                        {
                            "event_id": event.event_id,
                            "event_seq": event.event_seq,
                            "node": event.node,
                            "event_type": event.event_type,
                            "status": event.status,
                            "message": event.message,
                            "elapsed_ms": event.elapsed_ms,
                            "metadata": event.metadata_json,
                            "created_at": event.created_at,
                        }
                    ).model_dump(by_alias=True, mode="json")
                    yield (
                        f"id: {event.event_seq}\n"
                        f"event: {event.event_type.lower()}\n"
                        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                    )
            if not emitted:
                yield ": keepalive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _last_seen(after: int | None, last_event_id: str | None) -> int | None:
    if after is not None:
        return after
    if last_event_id and last_event_id.isdigit():
        return int(last_event_id)
    return None
