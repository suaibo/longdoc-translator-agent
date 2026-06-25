import re
from typing import Any

from app.schemas.parser import BlockKind, ParsedBlock

_SENTENCE_END = re.compile(r"[.!?。！？；;][\]\)）】'\"]*$")
_WORD_HYPHEN = re.compile(r"[A-Za-z]{2,}-$")
_CJK = re.compile(r"[\u3400-\u9fff]")
_JAPANESE = re.compile(r"[\u3040-\u30ff]")
_KOREAN = re.compile(r"[\uac00-\ud7af]")
_ARABIC = re.compile(r"[\u0600-\u06ff]")
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")


class BoundaryAnalysisService:
    """Finds only ambiguous boundaries; the LLM decides those candidates."""

    TEXT_KINDS = {
        BlockKind.PARAGRAPH,
        BlockKind.LIST_ITEM,
        BlockKind.REFERENCE,
        BlockKind.CAPTION,
        BlockKind.OTHER,
    }

    def detect_language(self, blocks: list[ParsedBlock]) -> str:
        text = "\n".join(block.text for block in blocks)[:20_000]
        script_counts = {
            "ja": len(_JAPANESE.findall(text)),
            "ko": len(_KOREAN.findall(text)),
            "ar": len(_ARABIC.findall(text)),
            "ru": len(_CYRILLIC.findall(text)),
        }
        language, count = max(script_counts.items(), key=lambda item: item[1])
        if count >= 4:
            return language
        if len(_CJK.findall(text)) >= 8:
            return "zh"
        lowered = f" {text.casefold()} "
        markers = {
            "fr": (" le ", " la ", " des ", " une ", " est "),
            "de": (" der ", " die ", " das ", " und ", " ist "),
            "es": (" el ", " los ", " una ", " que ", " para "),
            "pt": (" os ", " uma ", " que ", " para ", " não "),
            "en": (" the ", " and ", " of ", " to ", " is "),
        }
        scores = {
            code: sum(lowered.count(marker) for marker in language_markers)
            for code, language_markers in markers.items()
        }
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "en"

    def discover(self, blocks: list[ParsedBlock]) -> list[dict[str, Any]]:
        ordered = sorted(blocks, key=lambda block: block.order)
        candidates: list[dict[str, Any]] = []
        for left, right in zip(ordered, ordered[1:]):
            if left.kind not in self.TEXT_KINDS or right.kind not in self.TEXT_KINDS:
                continue
            page_break = (
                left.page_no is not None
                and right.page_no is not None
                and left.page_no != right.page_no
            )
            incomplete = not bool(_SENTENCE_END.search(left.text.strip()))
            hyphenated = bool(_WORD_HYPHEN.search(left.text.strip()))
            lowercase_start = bool(re.match(r"^[a-z]", right.text.strip()))
            parser_warning = bool(left.risks or right.risks)
            ambiguous = (
                page_break
                and (incomplete or hyphenated or lowercase_start or parser_warning)
            ) or (parser_warning and incomplete)
            if not ambiguous:
                continue
            reasons = [
                name
                for active, name in (
                    (page_break, "PAGE_BREAK"),
                    (incomplete, "INCOMPLETE_PUNCTUATION"),
                    (hyphenated, "HYPHENATED_WORD"),
                    (lowercase_start, "LOWERCASE_CONTINUATION"),
                    (parser_warning, "PARSER_WARNING"),
                )
                if active
            ]
            candidates.append(
                {
                    "leftBlockId": left.block_id,
                    "rightBlockId": right.block_id,
                    "left": left.text[-800:],
                    "right": right.text[:800],
                    "leftPage": left.page_no,
                    "rightPage": right.page_no,
                    "signals": reasons,
                }
            )
        return candidates
