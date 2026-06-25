from app.agent.graph import build_workflow
from app.agent.nodes import WorkflowNodes
from app.schemas.parser import BlockKind, ParsedBlock
from app.services.boundary_analysis import BoundaryAnalysisService


def test_cross_page_incomplete_sentence_becomes_llm_candidate() -> None:
    blocks = [
        ParsedBlock(
            block_id="left",
            kind=BlockKind.PARAGRAPH,
            text="The proposed method continues",
            markdown="The proposed method continues",
            order=0,
            page_no=1,
        ),
        ParsedBlock(
            block_id="right",
            kind=BlockKind.PARAGRAPH,
            text="with a second optimization stage.",
            markdown="with a second optimization stage.",
            order=1,
            page_no=2,
        ),
    ]
    service = BoundaryAnalysisService()

    candidates = service.discover(blocks)

    assert len(candidates) == 1
    assert candidates[0]["rightBlockId"] == "right"
    assert "PAGE_BREAK" in candidates[0]["signals"]
    assert service.detect_language(blocks) == "en"


def test_langgraph_contains_real_routes_loops_and_output_validation() -> None:
    graph = build_workflow().get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}

    assert ("parse_document", "parse_document") in edges
    assert ("discover_boundary_candidates", "analyze_semantic_boundaries") in edges
    assert ("discover_boundary_candidates", "split_sections") in edges
    assert ("analyze_semantic_boundaries", "fallback_boundary_analysis") in edges
    assert ("save_checkpoint", "translate_chunk") in edges
    assert ("mark_risks", "check_cross_chunk_coherence") in edges
    assert (
        "check_cross_chunk_coherence",
        "interrupt_for_high_risk_review",
    ) in edges
    assert ("validate_outputs", "generate_outputs") in edges


def test_boundary_retry_routes_to_fallback_after_limit(monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("BOUNDARY_LLM_MAX_RETRIES", "2")
    get_settings.cache_clear()
    try:
        assert (
            WorkflowNodes.route_after_boundary_analysis(
                {"boundary_analysis_failed": True, "boundary_retry_count": 2}
            )
            == "retry"
        )
        assert (
            WorkflowNodes.route_after_boundary_analysis(
                {"boundary_analysis_failed": True, "boundary_retry_count": 3}
            )
            == "fallback"
        )
    finally:
        get_settings.cache_clear()


def test_short_english_without_stopword_match_defaults_to_english() -> None:
    blocks = [
        ParsedBlock(
            block_id="short",
            kind=BlockKind.PARAGRAPH,
            text="Results show improved reliability across long-running tasks.",
            markdown="Results show improved reliability across long-running tasks.",
            order=0,
        )
    ]

    assert BoundaryAnalysisService().detect_language(blocks) == "en"
