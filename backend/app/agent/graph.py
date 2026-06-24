from langgraph.graph import END, START, StateGraph

from app.agent.nodes import WorkflowNodes
from app.agent.state import TranslationState


def build_workflow(checkpointer=None):
    nodes = WorkflowNodes()
    builder = StateGraph(TranslationState)
    builder.add_node("parse_document", nodes.parse_document)
    builder.add_node("split_sections", nodes.split_sections)
    builder.add_node("extract_terms", nodes.extract_terms)
    builder.add_node(
        "interrupt_for_term_review", nodes.interrupt_for_term_review
    )
    builder.add_node("translate_chunk", nodes.translate_chunk)
    builder.add_node("summarize_chunk_context", nodes.summarize_chunk_context)
    builder.add_node("mark_risks", nodes.mark_risks)
    builder.add_node("save_checkpoint", nodes.save_checkpoint)
    builder.add_node("generate_outputs", nodes.generate_outputs)
    builder.add_node("generate_report", nodes.generate_report)

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
    builder.add_edge("summarize_chunk_context", "mark_risks")
    builder.add_edge("mark_risks", "save_checkpoint")
    builder.add_edge("save_checkpoint", "translate_chunk")
    builder.add_edge("generate_outputs", "generate_report")
    builder.add_edge("generate_report", END)
    return builder.compile(checkpointer=checkpointer, name="longdoc-translator")
