from typing import Any, TypedDict


class TranslationState(TypedDict, total=False):
    job_id: str
    workflow_version: str
    current_chunk_id: str | None
    current_chunk_index: int | None
    previous_summary: str | None
    translation_done: bool
    cancelled: bool
    review_result: dict[str, Any] | None
