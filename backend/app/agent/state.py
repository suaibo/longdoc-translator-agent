from typing import Any, TypedDict


class TranslationState(TypedDict, total=False):
    job_id: str
    workflow_version: str
    source_language: str | None
    boundary_candidates: list[dict[str, Any]]
    boundary_decisions: list[dict[str, Any]]
    boundary_retry_count: int
    boundary_analysis_failed: bool
    parse_retry_count: int
    parse_error: str | None
    output_retry_count: int
    output_valid: bool
    output_error: str | None
    current_chunk_id: str | None
    current_chunk_index: int | None
    pretranslation_preview_id: str | None
    previous_summary: str | None
    translation_done: bool
    cancelled: bool
    quality_has_high_risk: bool
    review_result: dict[str, Any] | None
    style_review_result: dict[str, Any] | None
    risk_review_result: dict[str, Any] | None
    chapter_review_result: dict[str, Any] | None
