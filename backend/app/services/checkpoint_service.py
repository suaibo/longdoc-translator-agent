from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.models.agent_checkpoint import AgentCheckpoint
from app.models.translation_job import TranslationJob


class CheckpointService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def save(
        self,
        job_id: str,
        current_node: str,
        state: dict[str, Any],
        chunk_index: int | None = None,
    ) -> AgentCheckpoint:
        checkpoint = AgentCheckpoint(
            checkpoint_id=f"checkpoint_{uuid4().hex}",
            job_id=job_id,
            thread_id=job_id,
            current_node=current_node,
            chunk_index=chunk_index,
            state_snapshot={
                **state,
                "workflowVersion": get_settings().workflow_version,
            },
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(checkpoint)
        self.db.flush()
        return checkpoint

    def latest(self, job_id: str) -> AgentCheckpoint | None:
        return self.db.scalar(
            select(AgentCheckpoint)
            .where(AgentCheckpoint.job_id == job_id)
            .order_by(AgentCheckpoint.created_at.desc())
            .limit(1)
        )

    def assert_resume_compatible(self, job: TranslationJob) -> None:
        current = get_settings().workflow_version
        if job.workflow_version != current:
            raise AppError(
                ErrorCode.INVALID_STATE,
                f"工作流版本不兼容：任务={job.workflow_version}，当前={current}",
                status_code=409,
            )
        checkpoint = self.latest(job.job_id)
        if checkpoint:
            version = checkpoint.state_snapshot.get("workflowVersion")
            if version and version != current:
                raise AppError(
                    ErrorCode.INVALID_STATE,
                    f"检查点工作流版本不兼容：{version}",
                    status_code=409,
                )
