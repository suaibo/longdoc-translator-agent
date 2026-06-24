from contextlib import contextmanager
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from app.agent.graph import build_workflow
from app.core.config import get_settings


class WorkflowRunner:
    def run(self, job_id: str, resume_payload: dict[str, Any] | None = None) -> None:
        config = {"configurable": {"thread_id": job_id}}
        with self._checkpointer() as checkpointer:
            graph = build_workflow(checkpointer)
            snapshot = graph.get_state(config)
            # A resume payload continues an interrupt; None continues a failed or
            # restarted thread; only a new job receives initial graph state.
            if resume_payload is not None:
                graph.invoke(Command(resume=resume_payload), config=config)
            elif snapshot.values:
                graph.invoke(None, config=config)
            else:
                graph.invoke(
                    {
                        "job_id": job_id,
                        "workflow_version": get_settings().workflow_version,
                    },
                    config=config,
                )

    @contextmanager
    def _checkpointer(self):
        url = get_settings().database_url.replace(
            "postgresql+psycopg://", "postgresql://", 1
        )
        with PostgresSaver.from_conn_string(url) as saver:
            yield saver
