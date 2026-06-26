import html
import re
from pathlib import Path

from latex2mathml.converter import convert as latex_to_mathml

from app.models.document_chunk import DocumentChunk
from app.models.enums import ChunkType


class RenderService:
    def markdown_chunk(self, chunk: DocumentChunk, translated: bool) -> str:
        text = self._display_text(chunk, translated)
        return (text or "").strip()

    def html_chunk(
        self,
        chunk: DocumentChunk,
        translated: bool,
        asset_lookup: dict[str, str] | None = None,
    ) -> str:
        text = self._display_text(chunk, translated)
        text = text or ""
        if chunk.chunk_type == ChunkType.TABLE.value:
            return self._table_html(text)
        if chunk.chunk_type == ChunkType.FORMULA.value:
            return self._formula_html(
                text,
                self._source_asset_path(chunk, asset_lookup),
            )
        if chunk.chunk_type == ChunkType.CODE.value:
            return f"<pre><code>{html.escape(text)}</code></pre>"
        if chunk.chunk_type == ChunkType.PICTURE.value:
            return self._picture_html(text, self._source_asset_path(chunk, asset_lookup))
        return self._text_html(text)

    def document_html(
        self,
        title: str,
        body: str,
        bilingual: bool,
        target_language: str = "zh",
    ) -> str:
        mode = "双语对照" if bilingual else f"译文（{target_language.upper()}）"
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} - {mode}</title>
<style>
body {{ max-width: 980px; margin: 0 auto; padding: 32px; font: 16px/1.75 system-ui, sans-serif; color: #18201f; }}
h1,h2,h3,h4,h5,h6 {{ line-height: 1.3; margin-top: 1.8em; }}
.pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; border-top: 1px solid #ccd5d2; padding: 20px 0; }}
.source {{ color: #42504d; }}
table {{ border-collapse: collapse; width: 100%; overflow-wrap: anywhere; }}
th,td {{ border: 1px solid #aebbb7; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef3f1; }}
.formula {{ overflow-x: auto; padding: 12px; background: #f5f7f6; }}
.formula-asset {{ margin: 16px 0; padding: 12px; background: #f5f7f6; text-align: center; overflow-x: auto; }}
.formula-asset img {{ max-width: 100%; height: auto; }}
.figure-asset {{ margin: 18px 0; text-align: center; }}
.figure-asset img {{ max-width: 100%; height: auto; border: 1px solid #d8e0dd; }}
.inline-math {{ white-space: nowrap; }}
.author-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin: 16px 0; }}
.author-card {{ border: 1px solid #cbd5d2; border-radius: 6px; padding: 10px 12px; background: #fbfcfc; font-size: 14px; line-height: 1.45; overflow-wrap: anywhere; }}
.risk {{ border-left: 4px solid #a85d00; padding-left: 12px; }}
@media (max-width: 720px) {{ body {{ padding: 18px; }} .pair {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
{body}
</body>
</html>
"""

    def write_text_atomic(self, destination: Path, content: str) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(destination)

    def _text_html(self, text: str) -> str:
        parts: list[str] = []
        for paragraph in re.split(r"\n\s*\n", text):
            stripped = paragraph.strip()
            if not stripped:
                continue
            heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if heading:
                level = len(heading.group(1))
                parts.append(f"<h{level}>{html.escape(heading.group(2))}</h{level}>")
            else:
                escaped = self._inline_math_html(stripped).replace("\n", "<br>")
                parts.append(f"<p>{escaped}</p>")
        return "\n".join(parts)

    def _table_html(self, markdown: str) -> str:
        rows = [
            [html.escape(cell.strip()) for cell in line.strip("|").split("|")]
            for line in markdown.splitlines()
            if "|" in line
        ]
        if len(rows) < 2:
            return f"<pre>{html.escape(markdown)}</pre>"
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in rows[1]):
            rows.pop(1)
        if self._looks_like_author_grid(rows):
            cards = "".join(
                f'<div class="author-card">{cell}</div>'
                for row in rows
                for cell in row
                if cell.strip()
            )
            return f'<div class="author-grid">{cards}</div>'
        header, *body = rows
        head_html = "".join(f"<th>{cell}</th>" for cell in header)
        body_html = "".join(
            "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
            for row in body
        )
        return f'<div class="table-wrap"><table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table></div>'

    def _formula_html(self, latex: str, source_asset_path: str | None = None) -> str:
        clean = self._clean_formula(latex)
        if not clean or clean in {r"\n", r"\n\n"}:
            if source_asset_path:
                return (
                    '<figure class="formula-asset">'
                    f'<img src="{html.escape(source_asset_path)}" alt="公式原图">'
                    "<figcaption>公式由原文截图保留，请对照原始 PDF 复核。</figcaption>"
                    "</figure>"
                )
            return '<pre class="formula">公式解析为空，请对照原始 PDF 复核。</pre>'
        try:
            mathml = latex_to_mathml(clean)
            return f'<div class="formula">{mathml}</div>'
        except Exception:
            return f'<pre class="formula">{html.escape(clean)}</pre>'

    @staticmethod
    def _picture_html(caption: str, source_asset_path: str | None) -> str:
        escaped_caption = html.escape(caption.strip())
        if source_asset_path:
            figcaption = (
                f"<figcaption>{escaped_caption}</figcaption>"
                if escaped_caption
                else ""
            )
            return (
                '<figure class="figure-asset">'
                f'<img src="{html.escape(source_asset_path)}" alt="原文图片">'
                f"{figcaption}</figure>"
            )
        return (
            '<figure class="missing-asset">'
            f"<figcaption>{escaped_caption}</figcaption>"
            "<p>图片资产未由解析器导出，请对照原始文件。</p></figure>"
        )

    def _inline_math_html(self, text: str) -> str:
        protected: dict[str, str] = {}

        def replace(match: re.Match[str]) -> str:
            token = f"@@MATH_{len(protected)}@@"
            formula = self._clean_inline_formula(match.group(0))
            try:
                protected[token] = (
                    f'<span class="inline-math">{latex_to_mathml(formula)}</span>'
                )
            except Exception:
                protected[token] = (
                    f'<code class="inline-math">{html.escape(formula)}</code>'
                )
            return token

        pattern = re.compile(r"\\\(.+?\\\)|\\\[.+?\\\]|\$[^$\n]+\$", re.DOTALL)
        escaped = html.escape(pattern.sub(replace, text))
        for token, rendered in protected.items():
            escaped = escaped.replace(token, rendered)
        return escaped

    @staticmethod
    def _display_text(chunk: DocumentChunk, translated: bool) -> str:
        if translated and RenderService._translation_protected(chunk):
            return chunk.source_text or ""
        text = chunk.translated_text if translated else chunk.source_text
        return text or ""

    @staticmethod
    def _translation_protected(chunk: DocumentChunk) -> bool:
        metadata = chunk.structure_metadata or {}
        if metadata.get("translationProtected") is True:
            return True
        if chunk.chunk_type in {
            ChunkType.FORMULA.value,
            ChunkType.PICTURE.value,
            ChunkType.CODE.value,
        }:
            return True
        if chunk.chunk_type == ChunkType.TABLE.value:
            emails = re.findall(
                r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
                chunk.source_text or "",
            )
            return len(set(emails)) >= 2
        return False

    @staticmethod
    def _source_asset_path(
        chunk: DocumentChunk, asset_lookup: dict[str, str] | None = None
    ) -> str | None:
        metadata = chunk.structure_metadata or {}
        path = metadata.get("sourceAssetPath")
        if isinstance(path, str) and path:
            return asset_lookup.get(path, path) if asset_lookup else path
        if asset_lookup:
            for block_id in chunk.source_block_ids or []:
                if block_id in asset_lookup:
                    return asset_lookup[block_id]
        return None

    @staticmethod
    def _clean_formula(value: str) -> str:
        clean = value.strip()
        clean = re.sub(r"^\$\$\s*|\s*\$\$$", "", clean, flags=re.DOTALL).strip()
        clean = re.sub(r"^\\\(|\\\)$", "", clean).strip()
        clean = re.sub(r"^\\\[|\\\]$", "", clean).strip()
        return clean

    @staticmethod
    def _clean_inline_formula(value: str) -> str:
        value = value.strip()
        if value.startswith(r"\(") and value.endswith(r"\)"):
            return value[2:-2].strip()
        if value.startswith(r"\[") and value.endswith(r"\]"):
            return value[2:-2].strip()
        if value.startswith("$") and value.endswith("$"):
            return value[1:-1].strip()
        return value

    @staticmethod
    def _looks_like_author_grid(rows: list[list[str]]) -> bool:
        flattened = [cell for row in rows for cell in row if cell.strip()]
        emails = [
            cell
            for cell in flattened
            if re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", cell)
        ]
        return len(emails) >= 2 and len(flattened) <= 16
