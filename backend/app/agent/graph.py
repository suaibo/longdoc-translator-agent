import logging
from collections.abc import Callable
from time import perf_counter
from typing import Any

from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import WorkflowNodes
from app.agent.state import TranslationState
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
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
            elapsed_ms = _elapsed_ms(started)
            timeout = get_settings().workflow_node_timeout_seconds
            if timeout > 0 and elapsed_ms > timeout * 1000:
                raise AppError(
                    ErrorCode.INTERNAL_ERROR,
                    f"节点 {node_name} 超过时间预算 {timeout:g} 秒",
                    status_code=504,
                )
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
            elapsed_ms=elapsed_ms,
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

    node_map = {
        "parse_document": nodes.parse_document_safe,
        "fail_parse": nodes.fail_parse,
        "detect_language": nodes.detect_language,
        "discover_boundary_candidates": nodes.discover_boundary_candidates,
        "analyze_semantic_boundaries": nodes.analyze_semantic_boundaries,
        "fallback_boundary_analysis": nodes.fallback_boundary_analysis,
        "normalize_cross_page_text": nodes.normalize_cross_page_text,
        "split_sections": nodes.split_sections,
        "extract_terms": nodes.extract_terms,
        "interrupt_for_term_review": nodes.interrupt_for_term_review,
        "translate_chunk": nodes.translate_chunk,
        "mark_risks": nodes.mark_risks,
        "check_cross_chunk_coherence": nodes.check_cross_chunk_coherence,
        "summarize_chunk_context": nodes.summarize_chunk_context,
        "update_long_term_memory": nodes.update_long_term_memory,
        "interrupt_for_high_risk_review": nodes.interrupt_for_high_risk_review,
        "interrupt_for_chapter_review": nodes.interrupt_for_chapter_review,
        "save_checkpoint": nodes.save_checkpoint,
        "generate_outputs": nodes.generate_outputs,
        "validate_outputs": nodes.validate_outputs,
        "fail_output_validation": nodes.fail_output_validation,
        "generate_report": nodes.generate_report,
    }
    for name, node in node_map.items():
        builder.add_node(name, _instrument_node(name, node))

    builder.add_edge(START, "parse_document")
    builder.add_conditional_edges(
        "parse_document",
        nodes.route_after_parse,
        {
            "success": "detect_language",
            "retry": "parse_document",
            "failed": "fail_parse",
        },
    )
    builder.add_edge("detect_language", "discover_boundary_candidates")
    builder.add_conditional_edges(
        "discover_boundary_candidates",
        nodes.route_boundary_analysis,
        {
            "split": "split_sections",
            "analyze": "analyze_semantic_boundaries",
        },
    )
    builder.add_conditional_edges(
        "analyze_semantic_boundaries",
        nodes.route_after_boundary_analysis,
        {
            "normalize": "normalize_cross_page_text",
            "retry": "analyze_semantic_boundaries",
            "fallback": "fallback_boundary_analysis",
        },
    )
    builder.add_edge("normalize_cross_page_text", "split_sections")
    builder.add_edge("fallback_boundary_analysis", "split_sections")
    builder.add_edge("fail_parse", END)

    builder.add_edge("split_sections", "extract_terms")
    builder.add_edge("extract_terms", "interrupt_for_term_review")
    builder.add_edge("interrupt_for_term_review", "translate_chunk")
    builder.add_conditional_edges(
        "translate_chunk",
        nodes.route_after_translation,
        {
            "summarize": "mark_risks",
            "outputs": "generate_outputs",
            "cancelled": END,
        },
    )
    builder.add_edge("mark_risks", "check_cross_chunk_coherence")
    builder.add_conditional_edges(
        "check_cross_chunk_coherence",
        nodes.route_after_quality,
        {
            "review": "interrupt_for_high_risk_review",
            "summarize": "summarize_chunk_context",
        },
    )
    builder.add_edge("interrupt_for_high_risk_review", "summarize_chunk_context")
    builder.add_edge("summarize_chunk_context", "update_long_term_memory")
    builder.add_edge("update_long_term_memory", "interrupt_for_chapter_review")
    builder.add_edge("interrupt_for_chapter_review", "save_checkpoint")
    builder.add_edge("save_checkpoint", "translate_chunk")

    builder.add_edge("generate_outputs", "validate_outputs")
    builder.add_conditional_edges(
        "validate_outputs",
        nodes.route_after_output_validation,
        {
            "report": "generate_report",
            "retry": "generate_outputs",
            "failed": "fail_output_validation",
        },
    )
    builder.add_edge("fail_output_validation", END)
    builder.add_edge("generate_report", END)
    return builder.compile(checkpointer=checkpointer, name="longdoc-translator")
