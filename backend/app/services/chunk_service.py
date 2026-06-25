import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import ceil
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.models.document_chunk import DocumentChunk
from app.models.enums import ChunkStatus, ChunkType, JobStatus, RiskType
from app.models.risk_item import RiskItem
from app.models.translation_job import TranslationJob
from app.schemas.chunk import ChunkDraft
from app.schemas.parser import BlockKind, BlockRisk, ParsedBlock
from app.services.semantic_boundary import SemanticBoundaryService

ATOMIC_TYPES = {
    BlockKind.FORMULA: ChunkType.FORMULA,
    BlockKind.PICTURE: ChunkType.PICTURE,
    BlockKind.CODE: ChunkType.CODE,
}
PROTECTED_PATTERN = re.compile(
    r"(\$\$.*?\$\$|\$[^$\n]+\$|\\\(.*?\\\)|\\\[.*?\\\]|\[\d+(?:\s*[-,]\s*\d+)*\])",
    re.DOTALL,
)
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？；;؟؛])\s+|(?<=[。！？；])")
CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


@dataclass
class _ChunkBuffer:
    section_title: str | None
    section_path: list[str] = field(default_factory=list)
    parts: list[str] = field(default_factory=list)
    block_ids: list[str] = field(default_factory=list)
    risks: list[BlockRisk] = field(default_factory=list)
    pages: set[int] = field(default_factory=set)
    kinds: list[str] = field(default_factory=list)
    locations: list[dict[str, Any]] = field(default_factory=list)
    boundary_reason: str | None = None
    boundary_score: float | None = None

    def text(self) -> str:
        return "\n\n".join(part for part in self.parts if part.strip()).strip()


class ChunkService:
    def __init__(
        self,
        db: Session,
        max_tokens: int | None = None,
        max_table_rows: int | None = None,
        semantic_service: SemanticBoundaryService | None = None,
        boundary_decisions: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        settings = get_settings()
        self.db = db
        self.target_tokens = settings.chunk_target_tokens
        self.soft_max_tokens = settings.chunk_soft_max_tokens
        self.hard_max_tokens = settings.chunk_hard_max_tokens
        if max_tokens is not None:
            self.target_tokens = min(self.target_tokens, max_tokens)
            self.soft_max_tokens = max_tokens
            self.hard_max_tokens = max_tokens
        self.max_tokens = self.hard_max_tokens
        self.min_tokens = settings.chunk_min_tokens
        self.semantic_threshold = settings.semantic_boundary_threshold
        self.semantic_service = semantic_service or SemanticBoundaryService()
        self.boundary_decisions = boundary_decisions or {}
        self.max_table_rows = (
            settings.table_max_rows if max_table_rows is None else max_table_rows
        )
        if (
            self.target_tokens <= 0
            or self.soft_max_tokens < self.target_tokens
            or self.hard_max_tokens < self.soft_max_tokens
            or self.max_table_rows <= 0
        ):
            raise ValueError("chunk thresholds must be positive")

    def build_drafts(self, blocks: list[ParsedBlock]) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        buffer = _ChunkBuffer(section_title=None)
        ordered = sorted(blocks, key=lambda block: block.order)
        captions_by_ref = {
            str(block.metadata["docling_self_ref"]): block
            for block in ordered
            if block.kind == BlockKind.CAPTION
            and block.metadata.get("docling_self_ref")
        }
        referenced_caption_ids = {
            captions_by_ref[reference].block_id
            for block in ordered
            for reference in block.metadata.get("docling_caption_refs", [])
            if reference in captions_by_ref
        }
        index = 0

        while index < len(ordered):
            block = ordered[index]
            if block.kind in {BlockKind.TITLE, BlockKind.HEADING}:
                buffer.boundary_reason = "SECTION_BOUNDARY"
                self._flush_buffer(buffer, drafts)
                section_path = list(block.metadata.get("section_path", []))
                buffer = _ChunkBuffer(
                    section_title=block.text.strip() or None,
                    section_path=section_path or [block.text.strip()],
                )
                self._append_block(buffer, block)
                index += 1
                continue

            caption = None
            if block.kind == BlockKind.CAPTION:
                if block.block_id in referenced_caption_ids:
                    index += 1
                    continue
                if index + 1 < len(ordered):
                    next_block = ordered[index + 1]
                    if next_block.kind in {BlockKind.TABLE, BlockKind.PICTURE}:
                        caption = block
                        block = next_block
                        index += 1
            if block.kind in {BlockKind.TABLE, BlockKind.PICTURE} and caption is None:
                caption = self._referenced_caption(block, captions_by_ref)

            if block.kind == BlockKind.TABLE:
                buffer.boundary_reason = "ATOMIC_BLOCK"
                self._flush_buffer(buffer, drafts)
                drafts.extend(
                    self._build_table_drafts(
                        block,
                        buffer.section_title,
                        section_path=buffer.section_path,
                        caption=caption,
                    )
                )
            elif block.kind in ATOMIC_TYPES:
                buffer.boundary_reason = "ATOMIC_BLOCK"
                self._flush_buffer(buffer, drafts)
                drafts.append(
                    self._atomic_draft(
                        block,
                        buffer.section_title,
                        ATOMIC_TYPES[block.kind],
                        section_path=buffer.section_path,
                        caption=caption,
                    )
                )
            else:
                for piece in self._split_block(block):
                    candidate = f"{buffer.text()}\n\n{piece.markdown}".strip()
                    candidate_tokens = self.estimate_tokens(candidate)
                    decision = self.boundary_decisions.get(piece.block_id)
                    decision_name = str((decision or {}).get("decision", ""))
                    boundary_score = (
                        float(decision.get("confidence", 0)) if decision else None
                    )
                    force_continue = decision_name == "CONTINUE"
                    should_semantic_split = (
                        bool(buffer.parts)
                        and decision_name == "SPLIT"
                        and self.estimate_tokens(buffer.text()) >= self.min_tokens
                    )
                    if buffer.parts and candidate_tokens > self.hard_max_tokens:
                        buffer.boundary_reason = "TOKEN_HARD_LIMIT"
                        buffer.boundary_score = boundary_score
                        self._flush_buffer(buffer, drafts)
                    elif buffer.parts and (
                        should_semantic_split
                        or (
                            candidate_tokens > self.soft_max_tokens
                            and not force_continue
                        )
                    ):
                        buffer.boundary_reason = (
                            "LLM_SEMANTIC_SPLIT"
                            if should_semantic_split
                            else "TOKEN_SOFT_LIMIT"
                        )
                        buffer.boundary_score = boundary_score
                        if decision:
                            buffer.locations.append(
                                {
                                    "boundaryDecision": decision_name,
                                    "boundaryReason": decision.get("reason"),
                                }
                            )
                        self._flush_buffer(buffer, drafts)
                    piece_path = list(piece.metadata.get("section_path", []))
                    if piece_path:
                        buffer.section_path = piece_path
                    self._append_block(buffer, piece)
            index += 1

        buffer.boundary_reason = "END_OF_DOCUMENT"
        self._flush_buffer(buffer, drafts)
        indexed = [
            draft.model_copy(update={"chunk_index": chunk_index})
            for chunk_index, draft in enumerate(self._merge_small_drafts(drafts))
            if draft.source_text.strip()
        ]
        return indexed

    def create_chunks(
        self, job_id: str, blocks: list[ParsedBlock]
    ) -> list[DocumentChunk]:
        job = self.db.get(TranslationJob, job_id)
        if job is None:
            raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
        if job.status not in {JobStatus.UPLOADED.value, JobStatus.PARSED.value}:
            raise AppError(ErrorCode.INVALID_STATE, status_code=409)

        drafts = self.build_drafts(blocks)
        if not drafts:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "文档没有可切分内容",
                status_code=422,
            )
        existing = {
            chunk.chunk_index: chunk
            for chunk in self.db.scalars(
                select(DocumentChunk).where(DocumentChunk.job_id == job_id)
            )
        }
        now = datetime.now(timezone.utc)
        persisted: list[DocumentChunk] = []

        try:
            for draft in drafts:
                chunk = existing.get(draft.chunk_index)
                if chunk is None:
                    chunk = DocumentChunk(
                        chunk_id=self._stable_id(
                            "chunk", job_id, str(draft.chunk_index)
                        ),
                        job_id=job_id,
                        chunk_index=draft.chunk_index,
                        section_title=draft.section_title,
                        chunk_type=draft.chunk_type.value,
                        source_text=draft.source_text,
                        source_block_ids=draft.source_block_ids,
                        structure_metadata=draft.structure_metadata,
                        section_path=draft.section_path,
                        boundary_reason=draft.boundary_reason,
                        boundary_score=draft.boundary_score,
                        semantic_topic=draft.semantic_topic,
                        status=ChunkStatus.PENDING.value,
                        has_risk=bool(draft.risks),
                        risk_summary=self._risk_summary(draft.risks),
                        token_estimate=draft.token_estimate,
                        created_at=now,
                        updated_at=now,
                    )
                    self.db.add(chunk)
                else:
                    self._assert_chunk_can_be_rebuilt(chunk)
                    chunk.section_title = draft.section_title
                    chunk.chunk_type = draft.chunk_type.value
                    chunk.source_text = draft.source_text
                    chunk.source_block_ids = draft.source_block_ids
                    chunk.structure_metadata = draft.structure_metadata
                    chunk.section_path = draft.section_path
                    chunk.boundary_reason = draft.boundary_reason
                    chunk.boundary_score = draft.boundary_score
                    chunk.semantic_topic = draft.semantic_topic
                    chunk.has_risk = bool(draft.risks)
                    chunk.risk_summary = self._risk_summary(draft.risks)
                    chunk.token_estimate = draft.token_estimate
                    chunk.updated_at = now

                self.db.flush()
                self._replace_chunk_risks(job_id, chunk, draft, now)
                persisted.append(chunk)

            draft_indexes = {draft.chunk_index for draft in drafts}
            for chunk_index, chunk in existing.items():
                if chunk_index in draft_indexes:
                    continue
                self._assert_chunk_can_be_rebuilt(chunk)
                self.db.execute(
                    delete(RiskItem).where(RiskItem.chunk_id == chunk.chunk_id)
                )
                self.db.delete(chunk)

            job.status = JobStatus.PARSED.value
            job.current_stage = "split_sections"
            job.total_chunks = len(drafts)
            job.completed_chunks = 0
            job.progress_percent = 0
            job.updated_at = now
            self.db.commit()
            for chunk in persisted:
                self.db.refresh(chunk)
            return persisted
        except Exception:
            self.db.rollback()
            raise

    def _split_block(self, block: ParsedBlock) -> list[ParsedBlock]:
        if self.estimate_tokens(block.markdown) <= self.max_tokens:
            return [block]

        sentences = self._split_sentences(block.markdown)
        if len(sentences) <= 1:
            return [block]

        pieces: list[ParsedBlock] = []
        current: list[str] = []
        for sentence in sentences:
            candidate = self._join_sentences(current + [sentence])
            if current and self.estimate_tokens(candidate) > self.max_tokens:
                pieces.append(self._piece_from_block(block, pieces, current))
                current = [sentence]
            else:
                current.append(sentence)
        if current:
            pieces.append(self._piece_from_block(block, pieces, current))
        return pieces

    def _build_table_drafts(
        self,
        table: ParsedBlock,
        section_title: str | None,
        section_path: list[str],
        caption: ParsedBlock | None,
    ) -> list[ChunkDraft]:
        lines = [line for line in table.markdown.splitlines() if line.strip()]
        if len(lines) < 2 or not self._is_separator_row(lines[1]):
            return [
                self._atomic_draft(
                    table,
                    section_title,
                    ChunkType.TABLE,
                    section_path=section_path,
                    caption=caption,
                )
            ]

        header = lines[:2]
        rows = lines[2:]
        caption_text = caption.markdown.strip() if caption else ""
        base_text = self._render_table_group(caption_text, header, rows)
        if (
            len(rows) <= self.max_table_rows
            and self.estimate_tokens(base_text) <= self.max_tokens
        ):
            return [
                self._table_draft(
                    table,
                    section_title,
                    section_path,
                    caption,
                    header,
                    rows,
                    group_index=0,
                    group_count=1,
                )
            ]

        row_groups = self._group_table_rows(caption_text, header, rows)
        group_count = len(row_groups)
        return [
            self._table_draft(
                table,
                section_title,
                section_path,
                caption,
                header,
                group_rows,
                group_index=group_index,
                group_count=group_count,
            )
            for group_index, group_rows in enumerate(row_groups)
        ]

    def _group_table_rows(
        self, caption: str, header: list[str], rows: list[str]
    ) -> list[list[str]]:
        groups: list[list[str]] = []
        current: list[str] = []
        sizing_caption = f"{caption} (continued)" if caption else ""
        for row in rows:
            candidate = current + [row]
            rendered = self._render_table_group(sizing_caption, header, candidate)
            if current and (
                len(candidate) > self.max_table_rows
                or self.estimate_tokens(rendered) > self.max_tokens
            ):
                groups.append(current)
                current = [row]
            else:
                current = candidate
        if current or not groups:
            groups.append(current)
        return groups

    def _table_draft(
        self,
        table: ParsedBlock,
        section_title: str | None,
        section_path: list[str],
        caption: ParsedBlock | None,
        header: list[str],
        rows: list[str],
        group_index: int,
        group_count: int,
    ) -> ChunkDraft:
        original_caption = caption.markdown.strip() if caption else ""
        rendered_caption = original_caption
        if original_caption and group_index > 0:
            rendered_caption = f"{original_caption} (continued)"
        source_text = self._render_table_group(rendered_caption, header, rows)
        table_group_id = self._stable_id("table", table.block_id)
        block_ids = ([caption.block_id] if caption else []) + [table.block_id]
        risks = self._table_risks(caption, table)
        return ChunkDraft(
            section_title=section_title,
            chunk_type=ChunkType.TABLE,
            source_text=source_text,
            source_block_ids=block_ids,
            section_path=section_path,
            boundary_reason="TABLE_GROUP" if group_count > 1 else "ATOMIC_BLOCK",
            semantic_topic=self.semantic_service.topic(source_text),
            structure_metadata={
                "tableGroupId": table_group_id,
                "groupIndex": group_index,
                "groupCount": group_count,
                "originalTableBlockId": table.block_id,
                "caption": original_caption or None,
                "headerRows": header,
                "syntheticRepeat": group_index > 0,
                **self._page_metadata([item for item in [caption, table] if item]),
            },
            risks=risks,
            token_estimate=self.estimate_tokens(source_text),
        )

    def _atomic_draft(
        self,
        block: ParsedBlock,
        section_title: str | None,
        chunk_type: ChunkType,
        section_path: list[str] | None = None,
        caption: ParsedBlock | None = None,
    ) -> ChunkDraft:
        blocks = [item for item in [caption, block] if item is not None]
        source_text = "\n\n".join(item.markdown.strip() for item in blocks)
        metadata: dict[str, Any] = {
            "atomic": True,
            "blockKinds": [item.kind.value for item in blocks],
            **self._page_metadata(blocks),
        }
        if chunk_type == ChunkType.TABLE:
            metadata.update(
                {
                    "tableGroupId": self._stable_id("table", block.block_id),
                    "groupIndex": 0,
                    "groupCount": 1,
                    "originalTableBlockId": block.block_id,
                    "caption": caption.markdown.strip() if caption else None,
                    "syntheticRepeat": False,
                }
            )
        risks = self._merge_risks(*(item.risks for item in blocks))
        if chunk_type == ChunkType.TABLE:
            risks = self._ensure_risk(
                risks, RiskType.TABLE, "表格需保持行列结构并人工复核"
            )
        return ChunkDraft(
            section_title=section_title,
            chunk_type=chunk_type,
            source_text=source_text,
            source_block_ids=[item.block_id for item in blocks],
            section_path=section_path or list(block.metadata.get("section_path", [])),
            boundary_reason="ATOMIC_BLOCK",
            semantic_topic=self.semantic_service.topic(source_text),
            structure_metadata=metadata,
            risks=risks,
            token_estimate=self.estimate_tokens(source_text),
        )

    def _flush_buffer(self, buffer: _ChunkBuffer, drafts: list[ChunkDraft]) -> None:
        source_text = buffer.text()
        if not source_text:
            return
        drafts.append(
            ChunkDraft(
                section_title=buffer.section_title,
                chunk_type=ChunkType.TEXT,
                source_text=source_text,
                source_block_ids=list(dict.fromkeys(buffer.block_ids)),
                section_path=list(buffer.section_path),
                boundary_reason=buffer.boundary_reason or "TOKEN_SOFT_LIMIT",
                boundary_score=buffer.boundary_score,
                semantic_topic=self.semantic_service.topic(source_text),
                structure_metadata={
                    "atomic": False,
                    "blockKinds": list(buffer.kinds),
                    "pages": sorted(buffer.pages),
                    "blockLocations": list(buffer.locations),
                },
                risks=self._merge_risks(buffer.risks),
                token_estimate=self.estimate_tokens(source_text),
            )
        )
        buffer.parts.clear()
        buffer.block_ids.clear()
        buffer.risks.clear()
        buffer.pages.clear()
        buffer.kinds.clear()
        buffer.locations.clear()
        buffer.boundary_reason = None
        buffer.boundary_score = None

    def _merge_small_drafts(self, drafts: list[ChunkDraft]) -> list[ChunkDraft]:
        # A small fragment may merge only with adjacent text in the same section;
        # atomic tables/formulas and hard structure boundaries remain untouched.
        if len(drafts) < 2:
            return drafts
        merged: list[ChunkDraft] = []
        for draft in drafts:
            if (
                merged
                and draft.chunk_type == ChunkType.TEXT
                and merged[-1].chunk_type == ChunkType.TEXT
                and draft.section_path == merged[-1].section_path
                and draft.token_estimate < self.min_tokens
                and merged[-1].token_estimate + draft.token_estimate
                <= self.soft_max_tokens
            ):
                previous = merged.pop()
                source_text = f"{previous.source_text}\n\n{draft.source_text}".strip()
                merged.append(
                    previous.model_copy(
                        update={
                            "source_text": source_text,
                            "source_block_ids": list(
                                dict.fromkeys(
                                    previous.source_block_ids + draft.source_block_ids
                                )
                            ),
                            "structure_metadata": {
                                **previous.structure_metadata,
                                "mergedSmallFragment": True,
                            },
                            "boundary_reason": draft.boundary_reason,
                            "boundary_score": draft.boundary_score,
                            "semantic_topic": self.semantic_service.topic(source_text),
                            "risks": self._merge_risks(previous.risks, draft.risks),
                            "token_estimate": self.estimate_tokens(source_text),
                        }
                    )
                )
            else:
                merged.append(draft)
        return merged

    @staticmethod
    def _append_block(buffer: _ChunkBuffer, block: ParsedBlock) -> None:
        buffer.parts.append(block.markdown.strip())
        buffer.block_ids.append(
            str(block.metadata.get("splitFromBlockId", block.block_id))
        )
        buffer.risks.extend(block.risks)
        buffer.kinds.append(block.kind.value)
        if block.page_no is not None:
            buffer.pages.add(block.page_no)
        if block.page_no is not None or block.bbox is not None:
            buffer.locations.append(
                {
                    "blockId": str(
                        block.metadata.get("splitFromBlockId", block.block_id)
                    ),
                    "pageNo": block.page_no,
                    "bbox": (
                        block.bbox.model_dump(mode="json") if block.bbox else None
                    ),
                }
            )

    @staticmethod
    def _piece_from_block(
        block: ParsedBlock, pieces: list[ParsedBlock], sentences: list[str]
    ) -> ParsedBlock:
        text = ChunkService._join_sentences(sentences)
        metadata = {
            **block.metadata,
            "splitFromBlockId": block.block_id,
            "splitPartIndex": len(pieces),
        }
        return block.model_copy(
            update={
                "block_id": f"{block.block_id}_part_{len(pieces)}",
                "text": text,
                "markdown": text,
                "metadata": metadata,
            }
        )

    @staticmethod
    def _join_sentences(sentences: list[str]) -> str:
        result = ""
        for sentence in sentences:
            if not result:
                result = sentence
                continue
            # Chinese sentence boundaries are zero-width; do not invent spaces.
            separator = "" if result[-1] in "。！？；" else " "
            result = f"{result}{separator}{sentence}"
        return result.strip()

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        protected: dict[str, str] = {}

        def replace(match: re.Match[str]) -> str:
            key = f"__PROTECTED_{len(protected)}__"
            protected[key] = match.group(0)
            return key

        safe_text = PROTECTED_PATTERN.sub(replace, text)
        parts = [part.strip() for part in SENTENCE_BOUNDARY.split(safe_text)]
        restored: list[str] = []
        for part in parts:
            if not part:
                continue
            for key, value in protected.items():
                part = part.replace(key, value)
            restored.append(part)
        return restored

    @staticmethod
    def estimate_tokens(text: str) -> int:
        cjk_count = len(CJK_PATTERN.findall(text))
        remaining = CJK_PATTERN.sub("", text)
        latin_chars = len(re.sub(r"\s+", "", remaining))
        return max(1, cjk_count + ceil(latin_chars / 4))

    @staticmethod
    def _render_table_group(caption: str, header: list[str], rows: list[str]) -> str:
        parts = [caption] if caption else []
        parts.append("\n".join(header + rows))
        return "\n\n".join(parts)

    @staticmethod
    def _is_separator_row(line: str) -> bool:
        return bool(re.match(r"^\s*\|?\s*:?-{3,}", line))

    @staticmethod
    def _page_metadata(blocks: list[ParsedBlock]) -> dict[str, Any]:
        pages = sorted({block.page_no for block in blocks if block.page_no is not None})
        locations = [
            {
                "blockId": block.block_id,
                "pageNo": block.page_no,
                "bbox": block.bbox.model_dump(mode="json") if block.bbox else None,
            }
            for block in blocks
            if block.page_no is not None or block.bbox is not None
        ]
        return {"pages": pages, "blockLocations": locations}

    @staticmethod
    def _referenced_caption(
        block: ParsedBlock, captions_by_ref: dict[str, ParsedBlock]
    ) -> ParsedBlock | None:
        for reference in block.metadata.get("docling_caption_refs", []):
            if caption := captions_by_ref.get(reference):
                return caption
        return None

    def _table_risks(
        self, caption: ParsedBlock | None, table: ParsedBlock
    ) -> list[BlockRisk]:
        risks = self._merge_risks(
            *(item.risks for item in [caption, table] if item is not None)
        )
        return self._ensure_risk(risks, RiskType.TABLE, "表格需保持行列结构并人工复核")

    @staticmethod
    def _ensure_risk(
        risks: list[BlockRisk], risk_type: RiskType, message: str
    ) -> list[BlockRisk]:
        if not any(risk.risk_type == risk_type for risk in risks):
            return [*risks, BlockRisk(risk_type=risk_type, message=message)]
        return risks

    @staticmethod
    def _merge_risks(*risk_lists: list[BlockRisk]) -> list[BlockRisk]:
        unique: dict[tuple[RiskType, str], BlockRisk] = {}
        for risks in risk_lists:
            for risk in risks:
                unique[(risk.risk_type, risk.message)] = risk
        return list(unique.values())

    @staticmethod
    def _risk_summary(risks: list[BlockRisk]) -> str | None:
        if not risks:
            return None
        return "；".join(dict.fromkeys(risk.message for risk in risks))

    def _replace_chunk_risks(
        self,
        job_id: str,
        chunk: DocumentChunk,
        draft: ChunkDraft,
        created_at: datetime,
    ) -> None:
        self.db.execute(delete(RiskItem).where(RiskItem.chunk_id == chunk.chunk_id))
        for risk in draft.risks:
            self.db.add(
                RiskItem(
                    risk_id=self._stable_id(
                        "risk",
                        job_id,
                        chunk.chunk_id,
                        risk.risk_type.value,
                        risk.message,
                    ),
                    job_id=job_id,
                    chunk_id=chunk.chunk_id,
                    risk_type=risk.risk_type.value,
                    severity="MEDIUM",
                    message=risk.message,
                    source_excerpt=draft.source_text[:500],
                    metadata_json={
                        "sourceBlockIds": draft.source_block_ids,
                        **draft.structure_metadata,
                    },
                    created_at=created_at,
                )
            )

    @staticmethod
    def _assert_chunk_can_be_rebuilt(chunk: DocumentChunk) -> None:
        if chunk.status != ChunkStatus.PENDING.value:
            raise AppError(
                ErrorCode.INVALID_STATE,
                "已处理的 chunk 不能被重新切分覆盖",
                status_code=409,
            )

    @staticmethod
    def _stable_id(prefix: str, *parts: str) -> str:
        value = ":".join(parts)
        return f"{prefix}_{uuid5(NAMESPACE_URL, value).hex}"
