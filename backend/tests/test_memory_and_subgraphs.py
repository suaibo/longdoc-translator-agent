from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agent.structure_subgraphs import validate_structure
from app.models.document_chunk import DocumentChunk
from app.models.translation_job import TranslationJob
from app.schemas.llm import LLMResult, StoryEntity, StoryMemoryResult
from app.services.memory_service import MemoryService


class MemoryLLM:
    def extract_story_memory(self, original: str, translated: str):
        return (
            StoryMemoryResult(
                entities=[
                    StoryEntity(
                        entityType="CHARACTER",
                        sourceName="Alice",
                        translatedName="爱丽丝",
                        note="protagonist",
                    )
                ]
            ),
            LLMResult(content='{"entities": []}'),
        )


def test_novel_memory_persists_entities_and_chapter_summary(
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc)
    job = TranslationJob(
        job_id="job_memory",
        original_filename="novel.md",
        original_file_path="novel.md",
        mode="novel",
        status="TRANSLATING",
        current_stage="update_long_term_memory",
        created_at=now,
        updated_at=now,
    )
    chunk = DocumentChunk(
        chunk_id="chunk_memory",
        job_id=job.job_id,
        chunk_index=0,
        section_title="Chapter 1",
        section_path=["Chapter 1"],
        source_text="Alice arrived.",
        translated_text="爱丽丝到了。",
        context_summary="爱丽丝抵达。",
        status="COMPLETED",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([job, chunk])
    db_session.commit()

    service = MemoryService(db_session, llm=MemoryLLM())
    service.update(job.job_id, chunk)
    context = service.context(job.job_id)

    assert context["entities"][0]["translation"] == "爱丽丝"
    assert context["recentChapters"][0]["summary"] == "爱丽丝抵达。"


def test_structure_subgraphs_detect_damage() -> None:
    table_issues = validate_structure(
        "table",
        "| A | B |\n| - | - |\n| 1 | 2 |",
        "| 甲 | 乙 |",
    )
    formula_issues = validate_structure("formula", "$x+y$", "x+y")
    reference_issues = validate_structure("reference", "See [1].", "参见 1。")

    assert table_issues[0]["type"] == "TABLE"
    assert formula_issues[0]["type"] == "FORMULA"
    assert reference_issues[0]["type"] == "REFERENCE"
