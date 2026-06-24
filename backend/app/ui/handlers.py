from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import gradio as gr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models.document_chunk import DocumentChunk
from app.models.risk_item import RiskItem
from app.models.term_entry import TermEntry
from app.schemas.term import TermConfirmation
from app.services.job_service import JobService
from app.services.term_service import TermService
from app.services.worker_service import get_worker
from app.storage.paths import get_storage_paths


@contextmanager
def session_scope() -> Generator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def create_job(
    file_path: str | None, mode: str, ocr_mode: str = "auto"
) -> tuple[str, Any, str | None]:
    if not file_path:
        return "请先选择 PDF、Markdown 或 TXT 文件。", gr.update(), None

    source = Path(file_path)
    try:
        with session_scope() as db:
            job = JobService(db, get_storage_paths()).create_job_from_path(
                source, source.name, mode, ocr_mode
            )
            get_worker().enqueue(job.job_id)
            choices = _job_choices(JobService(db, get_storage_paths()).list_jobs())
            return (
                f"任务 `{job.job_id}` 已创建。",
                gr.update(choices=choices, value=job.job_id),
                job.job_id,
            )
    except AppError as exc:
        return exc.message, gr.update(), None
    except Exception as exc:
        return f"创建任务失败：{exc}", gr.update(), None


def list_job_choices() -> tuple[Any, str | None]:
    with session_scope() as db:
        service = JobService(db, get_storage_paths())
        choices = _job_choices(service.list_jobs())
    value = choices[0][1] if choices else None
    return gr.update(choices=choices, value=value), value


def select_job(job_id: str | None) -> str | None:
    return job_id


def cancel_job(job_id: str | None) -> str:
    if not job_id:
        return "请先选择任务。"
    try:
        with session_scope() as db:
            job = JobService(db, get_storage_paths()).cancel_job(job_id)
            return f"任务状态已更新为 `{job.status}`。"
    except AppError as exc:
        return exc.message
    except Exception as exc:
        return f"取消任务失败：{exc}"


def resume_job(job_id: str | None) -> str:
    if not job_id:
        return "请先选择任务。"
    try:
        get_worker().resume(job_id)
        return "任务已从最近检查点恢复。"
    except AppError as exc:
        return exc.message
    except Exception as exc:
        return f"恢复任务失败：{exc}"


def confirm_terms(job_id: str | None, rows: list[list[Any]]) -> str:
    if not job_id:
        return "请先选择任务。"
    try:
        confirmations = [
            TermConfirmation(
                term_id=str(row[0]),
                confirmed_translation=str(row[3] or row[2]),
                note=str(row[4]) if row[4] else None,
            )
            for row in rows
        ]
        with session_scope() as db:
            TermService(db).confirm(job_id, confirmations)
        get_worker().resume_review(job_id)
        return "术语已确认，翻译工作流已继续。"
    except (AppError, ValueError) as exc:
        return getattr(exc, "message", str(exc))
    except Exception as exc:
        return f"确认术语失败：{exc}"


def ocr_visibility(file_path: str | None) -> Any:
    return gr.update(visible=bool(file_path and Path(file_path).suffix.lower() == ".pdf"))


def refresh_dashboard(
    job_id: str | None,
) -> tuple[
    str,
    list[list[Any]],
    list[list[Any]],
    list[list[Any]],
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
    Any,
]:
    if not job_id:
        return "请选择任务。", [], [], [], None, None, None, None, None, None, None

    try:
        with session_scope() as db:
            service = JobService(db, get_storage_paths())
            job = service.get_job(job_id)
            terms = list(
                db.scalars(
                    select(TermEntry)
                    .where(TermEntry.job_id == job_id)
                    .order_by(TermEntry.source_term)
                )
            )
            chunks = list(
                db.scalars(
                    select(DocumentChunk)
                    .where(DocumentChunk.job_id == job_id)
                    .order_by(DocumentChunk.chunk_index)
                )
            )
            risks = list(
                db.scalars(
                    select(RiskItem)
                    .where(RiskItem.job_id == job_id)
                    .order_by(RiskItem.created_at)
                )
            )
            outputs = get_storage_paths()
            return (
                _job_markdown(job),
                [
                    [
                        term.term_id,
                        term.source_term,
                        term.suggested_translation,
                        term.confirmed_translation or "",
                        term.note or "",
                        term.confirmed,
                    ]
                    for term in terms
                ],
                [
                    [
                        chunk.chunk_index,
                        chunk.section_title or "",
                        chunk.chunk_type,
                        chunk.status,
                        chunk.token_estimate,
                        chunk.has_risk,
                    ]
                    for chunk in chunks
                ],
                [
                    [
                        risk.severity,
                        risk.risk_type,
                        risk.message,
                        risk.source_excerpt or "",
                    ]
                    for risk in risks
                ],
                _existing_output(outputs.output_file(job_id, "bilingual")),
                _existing_output(outputs.output_file(job_id, "translated")),
                _existing_output(outputs.output_file(job_id, "report")),
                _existing_output(outputs.output_file(job_id, "bilingual_html")),
                _existing_output(outputs.output_file(job_id, "translated_html")),
                _existing_output(outputs.output_file(job_id, "package")),
                _existing_output(Path(job.original_file_path)),
            )
    except AppError as exc:
        return exc.message, [], [], [], None, None, None, None, None, None, None
    except Exception as exc:
        return (
            f"刷新失败：{exc}",
            [],
            [],
            [],
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )


def _job_choices(jobs: list[Any]) -> list[tuple[str, str]]:
    return [
        (f"{job.original_filename} · {job.status} · {job.job_id}", job.job_id)
        for job in jobs
    ]


def _job_markdown(job: Any) -> str:
    error = (
        f"\n\n**错误：** `{job.error_code or ''}` {job.error_message or ''}"
        if job.error_code or job.error_message
        else ""
    )
    return (
        f"### {job.original_filename}\n"
        f"- 任务 ID：`{job.job_id}`\n"
        f"- 状态：**{job.status}**\n"
        f"- 当前阶段：`{job.current_stage}`\n"
        f"- Chunk：{job.completed_chunks} / {job.total_chunks}\n"
        f"- 进度：{job.progress_percent:.1f}%"
        f"{error}"
    )


def _existing_output(path: Path) -> str | None:
    return str(path) if path.is_file() else None
