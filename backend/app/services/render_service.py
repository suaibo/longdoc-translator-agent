import html
import re
from pathlib import Path

from latex2mathml.converter import convert as latex_to_mathml

from app.models.document_chunk import DocumentChunk
from app.models.enums import ChunkType


class RenderService:
    def markdown_chunk(self, chunk: DocumentChunk, translated: bool) -> str:
        text = chunk.translated_text if translated else chunk.source_text
        return (text or "").strip()

    def html_chunk(self, chunk: DocumentChunk, translated: bool) -> str:
        text = chunk.translated_text if translated else chunk.source_text
        text = text or ""
        if chunk.chunk_type == ChunkType.TABLE.value:
            return self._table_html(text)
        if chunk.chunk_type == ChunkType.FORMULA.value:
            return self._formula_html(text)
        if chunk.chunk_type == ChunkType.CODE.value:
            return f"<pre><code>{html.escape(text)}</code></pre>"
        if chunk.chunk_type == ChunkType.PICTURE.value:
            return (
                '<figure class="missing-asset">'
                f"<figcaption>{html.escape(text)}</figcaption>"
                "<p>图片资产未由解析器导出，请对照原始文件。</p></figure>"
            )
        return self._text_html(text)

    def document_html(self, title: str, body: str, bilingual: bool) -> str:
        mode = "双语对照" if bilingual else "中文译文"
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
                parts.append(
                    f"<h{level}>{html.escape(heading.group(2))}</h{level}>"
                )
            else:
                escaped = html.escape(stripped).replace("\n", "<br>")
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
        header, *body = rows
        head_html = "".join(f"<th>{cell}</th>" for cell in header)
        body_html = "".join(
            "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
            for row in body
        )
        return f"<div class=\"table-wrap\"><table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table></div>"

    def _formula_html(self, latex: str) -> str:
        clean = re.sub(r"^\$\$|\$\$$", "", latex.strip()).strip()
        try:
            mathml = latex_to_mathml(clean)
            return f'<div class="formula">{mathml}</div>'
        except Exception:
            return f'<pre class="formula">{html.escape(clean)}</pre>'
