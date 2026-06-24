import re
from collections import defaultdict

from app.models.enums import RiskType
from app.schemas.parser import BlockKind, BlockRisk, ParsedBlock


class LayoutNormalizer:
    def __init__(self, long_paragraph_chars: int = 2000) -> None:
        self.long_paragraph_chars = long_paragraph_chars

    def normalize(self, blocks: list[ParsedBlock]) -> list[ParsedBlock]:
        filtered = self._remove_headers_and_footers(blocks)
        ordered = self._fix_page_reading_order(filtered)
        return [self._mark_risks(block, index) for index, block in enumerate(ordered)]

    def _remove_headers_and_footers(
        self, blocks: list[ParsedBlock]
    ) -> list[ParsedBlock]:
        page_count = len(
            {block.page_no for block in blocks if block.page_no is not None}
        )
        edge_text_pages: dict[str, set[int]] = defaultdict(set)
        for block in blocks:
            if self._is_page_edge(block) and block.page_no is not None:
                edge_text_pages[self._normalized_text(block.text)].add(block.page_no)

        repeated_threshold = max(2, (page_count + 1) // 2)
        repeated_edge_texts = {
            text
            for text, pages in edge_text_pages.items()
            if text and len(pages) >= repeated_threshold
        }
        return [
            block
            for block in blocks
            if not self._explicit_furniture(block)
            and not (
                self._is_page_edge(block)
                and self._normalized_text(block.text) in repeated_edge_texts
            )
        ]

    def _fix_page_reading_order(self, blocks: list[ParsedBlock]) -> list[ParsedBlock]:
        without_page = [block for block in blocks if block.page_no is None]
        by_page: dict[int, list[ParsedBlock]] = defaultdict(list)
        for block in blocks:
            if block.page_no is not None:
                by_page[block.page_no].append(block)

        result = list(without_page)
        for page_no in sorted(by_page):
            result.extend(self._normalize_page(by_page[page_no]))
        return result

    def _normalize_page(self, blocks: list[ParsedBlock]) -> list[ParsedBlock]:
        positioned = [block for block in blocks if block.bbox is not None]
        unpositioned = [block for block in blocks if block.bbox is None]
        if not self._has_two_columns(positioned):
            return sorted(positioned, key=self._vertical_key) + unpositioned

        ordered: list[ParsedBlock] = []
        column_segment: list[ParsedBlock] = []
        for block in sorted(positioned, key=self._vertical_key):
            if self._column_side(block) is None:
                ordered.extend(self._flush_columns(column_segment))
                column_segment = []
                ordered.append(block)
            else:
                column_segment.append(block)
        ordered.extend(self._flush_columns(column_segment))
        ordered.extend(unpositioned)
        return ordered

    def _has_two_columns(self, blocks: list[ParsedBlock]) -> bool:
        left = [block for block in blocks if self._column_side(block) == "left"]
        right = [block for block in blocks if self._column_side(block) == "right"]
        if not left or not right:
            return False
        left_range = self._vertical_range(left)
        right_range = self._vertical_range(right)
        return max(left_range[0], right_range[0]) < min(left_range[1], right_range[1])

    def _flush_columns(self, blocks: list[ParsedBlock]) -> list[ParsedBlock]:
        if not blocks:
            return []
        left = sorted(
            (block for block in blocks if self._column_side(block) == "left"),
            key=self._vertical_key,
        )
        right = sorted(
            (block for block in blocks if self._column_side(block) == "right"),
            key=self._vertical_key,
        )
        reordered = left + right
        if len(left) and len(right):
            return [self._with_layout_adjustment(block) for block in reordered]
        return reordered

    def _mark_risks(self, block: ParsedBlock, order: int) -> ParsedBlock:
        risks = list(block.risks)
        if block.kind == BlockKind.TABLE:
            risks.append(
                BlockRisk(
                    risk_type=RiskType.TABLE, message="表格需保持行列结构并人工复核"
                )
            )
        if block.kind == BlockKind.FORMULA or self._contains_formula(block.text):
            risks.append(
                BlockRisk(
                    risk_type=RiskType.FORMULA, message="公式需检查符号与编号是否完整"
                )
            )
        if block.kind == BlockKind.REFERENCE or self._contains_references(block.text):
            risks.append(
                BlockRisk(
                    risk_type=RiskType.REFERENCE,
                    message="引用密集片段需检查编号与作者年份对应关系",
                )
            )
        if (
            block.kind == BlockKind.PARAGRAPH
            and len(block.text) > self.long_paragraph_chars
        ):
            risks.append(
                BlockRisk(
                    risk_type=RiskType.LONG_PARAGRAPH,
                    message="超长段落需在切块阶段按句边界拆分",
                )
            )
        if block.metadata.get("layout_adjusted"):
            risks.append(
                BlockRisk(
                    risk_type=RiskType.STRUCTURE,
                    message="检测到双栏版面，已按左栏后右栏修正阅读顺序",
                )
            )
        return block.model_copy(
            update={"order": order, "risks": self._deduplicate_risks(risks)}
        )

    @staticmethod
    def _with_layout_adjustment(block: ParsedBlock) -> ParsedBlock:
        metadata = {**block.metadata, "layout_adjusted": True}
        return block.model_copy(update={"metadata": metadata})

    @staticmethod
    def _explicit_furniture(block: ParsedBlock) -> bool:
        return block.metadata.get("docling_label") in {"page_header", "page_footer"}

    @staticmethod
    def _is_page_edge(block: ParsedBlock) -> bool:
        if block.bbox is None or block.bbox.page_height <= 0:
            return False
        return (
            block.bbox.top <= block.bbox.page_height * 0.1
            or block.bbox.bottom >= block.bbox.page_height * 0.9
        )

    @staticmethod
    def _column_side(block: ParsedBlock) -> str | None:
        bbox = block.bbox
        if bbox is None or bbox.page_width <= 0 or bbox.width > bbox.page_width * 0.6:
            return None
        if bbox.center_x < bbox.page_width * 0.48:
            return "left"
        if bbox.center_x > bbox.page_width * 0.52:
            return "right"
        return None

    @staticmethod
    def _vertical_range(blocks: list[ParsedBlock]) -> tuple[float, float]:
        return (
            min(block.bbox.top for block in blocks if block.bbox is not None),
            max(block.bbox.bottom for block in blocks if block.bbox is not None),
        )

    @staticmethod
    def _vertical_key(block: ParsedBlock) -> tuple[float, float]:
        if block.bbox is None:
            return (float("inf"), float("inf"))
        return (block.bbox.top, block.bbox.left)

    @staticmethod
    def _normalized_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().casefold()

    @staticmethod
    def _contains_formula(text: str) -> bool:
        return bool(re.search(r"\$[^$]+\$|\\\(.+?\\\)|\\\[.+?\\\]", text, re.DOTALL))

    @staticmethod
    def _contains_references(text: str) -> bool:
        numbered = re.findall(r"\[\d+(?:\s*[-,]\s*\d+)*\]", text)
        author_year = re.findall(
            r"\([A-Z][A-Za-z-]+(?: et al\.)?,?\s+\d{4}[a-z]?\)", text
        )
        return len(numbered) + len(author_year) >= 2

    @staticmethod
    def _deduplicate_risks(risks: list[BlockRisk]) -> list[BlockRisk]:
        unique: dict[tuple[RiskType, str], BlockRisk] = {}
        for risk in risks:
            unique[(risk.risk_type, risk.message)] = risk
        return list(unique.values())
