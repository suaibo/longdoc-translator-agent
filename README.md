# LongDoc Translator Agent

Agent-powered long document translator for academic papers and novels, with structured parsing, terminology review, checkpointed translation workflow, and bilingual report export.

## Overview

LongDoc Translator Agent is a structured translation workflow for long documents. The MVP focuses on academic paper translation, while the architecture leaves room for a future novel translation mode with sliding-window memory for character names, places, style, and plot continuity.

The project is designed as an AI Agent engineering demo rather than a simple "translate this text" wrapper. It emphasizes document parsing, terminology consistency, human-in-the-loop review, checkpointed execution, and exportable translation reports.

## MVP Scope

- Upload PDF, Markdown, or TXT documents.
- Convert documents into structured Markdown with Docling.
- Split long documents by sections and paragraphs.
- Extract key terminology before translation.
- Pause for human terminology review and editing.
- Translate chunks with confirmed terminology.
- Maintain context through section summaries and previous-chunk summaries.
- Save progress with SQLite checkpoints.
- Resume failed translation jobs from the last completed chunk.
- Export:
  - bilingual Markdown
  - Chinese Markdown
  - translation report

## Tech Stack

- Backend: FastAPI
- Agent workflow: LangGraph
- Persistence: SQLite
- Document parsing: Docling
- LLM interface: OpenAI-compatible API
- Frontend: React + Vite

## Agent Workflow

```text
parse_document
-> split_sections
-> extract_terms
-> interrupt_for_term_review
-> translate_chunk
-> summarize_chunk_context
-> mark_risks
-> generate_outputs
-> generate_report
```

The first human-in-the-loop checkpoint is terminology review. The agent extracts candidate terms and suggested translations, then waits for user confirmation before continuing the translation job.

## Why This Project

Long document translation has several engineering challenges that are not visible in short text translation:

- document structure preservation
- terminology consistency
- table and formula risk handling
- long-context continuity
- resumable execution
- human review at high-risk steps
- progress and cost reporting

This project uses an Agent workflow to make these steps explicit, observable, and recoverable.

## Planned Modes

### Paper Mode

The MVP mode. It focuses on academic papers, theses, and technical reports.

Key concerns:

- section structure
- terminology consistency
- table preservation
- bilingual review
- translation progress report

### Novel Mode

Planned for a later version.

Key concerns:

- character name consistency
- place and setting memory
- tone and style continuity
- chapter-level sliding window memory
- long-running checkpointed translation

## Project Status

Planning and initial implementation stage.

The first milestone is a web console that can upload a sample paper, extract terms, pause for terminology review, translate chunks, and export bilingual Markdown plus a translation report.

## License

MIT
