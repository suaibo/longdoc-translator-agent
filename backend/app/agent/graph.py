import logging
from collections.abc import Callable
from time import perf_counter
from typing import Any

from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import WorkflowNodes
from app.agent.state import TranslationState
from app.db.session import SessionLocal
from app.core.telemetry import span
from app.services.event_service import EventService

logger = logging.getLogger(__name__)


def _instrument_node(
    node_name: str,
    node: Callable[[TranslationState], dict[str, Any]],
) -> Callable[[TranslationState], dict[str, Any]]:
    """Persist a uniform lifecycle timeline without coupling nodes to observability."""

    def wrapped(state: TranslationState) -> dict[str, Any]:
        job_id = state["job_id"]
        started = perf_counter()
        _record_event(job_id, node_name, "STARTED")
        try:
            with span(
                f"workflow.{node_name}",
                job_id=job_id,
                workflow_node=node_name,
            ):
                result = node(state)
        except GraphInterrupt:
            _record_event(
                job_id,
                node_name,
                "INTERRUPTED",
                elapsed_ms=_elapsed_ms(started),
                message="等待人工确认",
            )
            raise
        except Exception as exc:
            _record_event(
                job_id,
                node_name,
                "FAILED",
                elapsed_ms=_elapsed_ms(started),
                message=str(exc),
            )
            raise
        _record_event(
            job_id,
            node_name,
            "COMPLETED",
            elapsed_ms=_elapsed_ms(started),
        )
        return result

    return wrapped


def _record_event(
    job_id: str,
    node: str,
    status: str,
    *,
    elapsed_ms: int | None = None,
    message: str | None = None,
) -> None:
    # Observability must never replace the original workflow error.
    try:
        with SessionLocal() as db:
            EventService(db).record(
                job_id,
                node,
                "NODE",
                status,
                elapsed_ms=elapsed_ms,
                message=message,
            )
    except Exception:
        logger.exception("Failed to persist workflow event for %s/%s", job_id, node)


def _elapsed_ms(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))


def build_workflow(checkpointer=None):
    nodes = WorkflowNodes()
    builder = StateGraph(TranslationState)
    builder.add_node(
        "parse_document", _instrument_node("parse_document", nodes.parse_document)
    )
    builder.add_node(
        "split_sections", _instrument_node("split_sections", nodes.split_sections)
    )
    builder.add_node(
        "extract_terms", _instrument_node("extract_terms", nodes.extract_terms)
    )
    builder.add_node(
        "interrupt_for_term_review",
        _instrument_node(
            "interrupt_for_term_review", nodes.interrupt_for_term_review
        ),
    )
    builder.add_node(
        "translate_chunk", _instrument_node("translate_chunk", nodes.translate_chunk)
    )
    builder.add_node(
        "summarize_chunk_context",
        _instrument_node(
            "summarize_chunk_context", nodes.summarize_chunk_context
        ),
    )
    builder.add_node(
        "mark_risks", _instrument_node("mark_risks", nodes.mark_risks)
    )
    builder.add_node(
        "update_long_term_memory",
        _instrument_node(
            "update_long_term_memory", nodes.update_long_term_memory
        ),
    )
    builder.add_node(
        "interrupt_for_high_risk_review",
        _instrument_node(
            "interrupt_for_high_risk_review",
            nodes.interrupt_for_high_risk_review,
        ),
    )
    builder.add_node(
        "interrupt_for_chapter_review",
        _instrument_node(
            "interrupt_for_chapter_review",
            nodes.interrupt_for_chapter_review,
        ),
    )
    builder.add_node(
        "save_checkpoint", _instrument_node("save_checkpoint", nodes.save_checkpoint)
    )
    builder.add_node(
        "generate_outputs",
        _instrument_node("generate_outputs", nodes.generate_outputs),
    )
    builder.add_node(
        "generate_report",
        _instrument_node("generate_report", nodes.generate_report),
    )

    builder.add_edge(START, "parse_document")
    builder.add_edge("parse_document", "split_sections")
    builder.add_edge("split_sections", "extract_terms")
    builder.add_edge("extract_terms", "interrupt_for_term_review")
    builder.add_edge("interrupt_for_term_review", "translate_chunk")
    builder.add_conditional_edges(
        "translate_chunk",
        nodes.route_after_translation,
        {
            "summarize": "summarize_chunk_context",
            "outputs": "generate_outputs",
            "cancelled": END,
        },
    )
    builder.add_edge("summarize_chunk_context", "update_long_term_memory")
    builder.add_edge("update_long_term_memory", "mark_risks")
    builder.add_edge("mark_risks", "interrupt_for_high_risk_review")
    builder.add_edge(
        "interrupt_for_high_risk_review", "interrupt_for_chapter_review"
    )
    builder.add_edge("interrupt_for_chapter_review", "save_checkpoint")
    builder.add_edge("save_checkpoint", "translate_chunk")
    builder.add_edge("generate_outputs", "generate_report")
    builder.add_edge("generate_report", END)
    return builder.compile(checkpointer=checkpointer, name="longdoc-translator")
