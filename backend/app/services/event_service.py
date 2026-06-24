from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workflow_event import WorkflowEvent


class EventService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        job_id: str,
        node: str,
        event_type: str,
        status: str,
        *,
        message: str | None = None,
        elapsed_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowEvent:
        event = WorkflowEvent(
            event_id=f"event_{uuid4().hex}",
            job_id=job_id,
            node=node,
            event_type=event_type,
            status=status,
            message=message,
            elapsed_ms=elapsed_ms,
            metadata_json=metadata or {},
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        self.db.commit()
        return event

    def list_events(self, job_id: str) -> list[WorkflowEvent]:
        return list(
            self.db.scalars(
                select(WorkflowEvent)
                .where(WorkflowEvent.job_id == job_id)
                .order_by(WorkflowEvent.created_at)
            )
        )
