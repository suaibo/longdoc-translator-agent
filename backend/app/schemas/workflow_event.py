from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.job import to_camel


class WorkflowEventResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    event_id: str
    node: str
    event_type: str
    status: str
    message: str | None
    elapsed_ms: int | None
    metadata: dict[str, Any]
    created_at: datetime
