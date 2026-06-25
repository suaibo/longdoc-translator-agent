from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.core.response import success
from app.db.session import get_db
from app.schemas.workflow_event import WorkflowEventResponse
from app.services.event_service import EventService
from app.services.job_service import JobService
from app.storage.paths import get_storage_paths

router = APIRouter(prefix="/api/jobs", tags=["events"])


@router.get("/{job_id}/events")
def list_events(
    job_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
    events = EventService(db).list_events(job_id)
    data = [
        WorkflowEventResponse.model_validate(
            {
                "event_id": event.event_id,
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
