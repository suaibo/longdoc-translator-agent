from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chapter_memory import ChapterMemory
from app.models.document_chunk import DocumentChunk
from app.models.story_memory import StoryMemory
from app.services.budget_service import BudgetService
from app.services.llm_service import LLMService
from app.services.metric_service import MetricService


class MemoryService:
    def __init__(self, db: Session, llm: LLMService | None = None) -> None:
        self.db = db
        self.llm = llm

    def context(self, job_id: str) -> dict:
        entities = list(
            self.db.scalars(
                select(StoryMemory)
                .where(StoryMemory.job_id == job_id)
                .order_by(StoryMemory.last_seen_chunk.desc())
                .limit(100)
            )
        )
        chapters = list(
            self.db.scalars(
                select(ChapterMemory)
                .where(ChapterMemory.job_id == job_id)
                .order_by(ChapterMemory.updated_at.desc())
                .limit(5)
            )
        )
        return {
            "entities": [
                {
                    "type": item.entity_type,
                    "source": item.source_name,
                    "translation": item.translated_name,
                    "note": item.note,
                }
                for item in entities
            ],
            "recentChapters": [
                {"sectionPath": item.section_path, "summary": item.summary}
                for item in chapters
            ],
        }

    def update(self, job_id: str, chunk: DocumentChunk) -> None:
        if not chunk.translated_text:
            return
        llm = self.llm or LLMService()
        BudgetService(self.db).assert_available(job_id)
        memory, result = llm.extract_story_memory(
            chunk.source_text, chunk.translated_text
        )
        MetricService(self.db).record(job_id, result, chunk_id=chunk.chunk_id)
        now = datetime.now(timezone.utc)
        for entity in memory.entities:
            entity_type = entity.entity_type.upper()
            if entity_type not in {"CHARACTER", "PLACE", "SETTING"}:
                continue
            item = self.db.scalar(
                select(StoryMemory).where(
                    StoryMemory.job_id == job_id,
                    StoryMemory.entity_type == entity_type,
                    StoryMemory.source_name == entity.source_name,
                )
            )
            if item is None:
                item = StoryMemory(
                    memory_id=f"memory_{uuid5(NAMESPACE_URL, f'{job_id}:{entity_type}:{entity.source_name}').hex}",
                    job_id=job_id,
                    entity_type=entity_type,
                    source_name=entity.source_name,
                    translated_name=entity.translated_name,
                    note=entity.note,
                    first_seen_chunk=chunk.chunk_index,
                    last_seen_chunk=chunk.chunk_index,
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(item)
            else:
                item.translated_name = entity.translated_name
                item.note = entity.note or item.note
                item.last_seen_chunk = chunk.chunk_index
                item.updated_at = now
        self._update_chapter(job_id, chunk, now)
        self.db.commit()

    def _update_chapter(
        self, job_id: str, chunk: DocumentChunk, now: datetime
    ) -> None:
        section_path = chunk.section_path or [chunk.section_title or "正文"]
        section_key = "/".join(section_path)
        item = self.db.scalar(
            select(ChapterMemory).where(
                ChapterMemory.job_id == job_id,
                ChapterMemory.section_key == section_key,
            )
        )
        summary = chunk.context_summary or chunk.translated_text[:300]
        if item is None:
            item = ChapterMemory(
                chapter_memory_id=f"chapter_{uuid5(NAMESPACE_URL, f'{job_id}:{section_key}').hex}",
                job_id=job_id,
                section_key=section_key,
                section_path=section_path,
                summary=summary,
                updated_at=now,
            )
            self.db.add(item)
        else:
            item.summary = f"{item.summary}\n{summary}"[-2000:]
            item.updated_at = now
