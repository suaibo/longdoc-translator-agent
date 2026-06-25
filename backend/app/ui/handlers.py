from collections.abc import Generator
from contextlib import contextmanager
from html import escape
from pathlib import Path
from typing import Any

import gradio as gr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.db.session import SessionLocal
from app.models.document_chunk import DocumentChunk
from app.models.risk_item import RiskItem
from app.models.term_entry import TermEntry
from app.schemas.term import TermConfirmation
from app.services.auth_service import AuthService
from app.services.event_service import EventService
from app.services.job_service import JobService
from app.services.review_service import ReviewService
from app.services.term_service import TermService
from app.services.worker_service import get_worker
from app.storage.object_store import ObjectStorageService
from app.storage.paths import get_storage_paths

STATUS_LABELS = {
    "UPLOADED": "等待处理",
    "PARSED": "解析完成",
    "WAITING_TERM_REVIEW": "等待术语确认",
    "WAITING_RISK_REVIEW": "等待风险审核",
    "WAITING_CHAPTER_REVIEW": "等待章节审核",
    "TRANSLATING": "翻译中",
    "COMPLETED": "已完成",
    "FAILED": "失败，可恢复",
    "CANCELLED": "已取消",
}
RISK_LABELS = {
    "TABLE": "表格结构",
    "FORMULA": "公式结构",
    "REFERENCE": "引用完整性",
    "STRUCTURE": "版面结构",
    "LONG_PARAGRAPH": "超长段落",
    "PARSER_WARNING": "解析异常",
    "OMISSION": "疑似漏译",
    "TERMINOLOGY": "术语不一致",
    "NUMBER_MISMATCH": "数字或单位不一致",
    "FORMULA_MISMATCH": "公式不一致",
    "CITATION_MISMATCH": "引用不一致",
    "INCOMPLETE_SENTENCE": "句子可能不完整",
    "CROSS_PAGE_UNCERTAIN": "跨页语义不确定",
    "SEMANTIC_DISCONTINUITY": "上下文不连贯",
    "FORCED_TOKEN_SPLIT": "达到长度上限后强制切分",
    "OCR_TEXT_BREAK": "OCR 文本断裂",
    "BOUNDARY_MODEL_FAILED": "语义判断已降级",
}


@contextmanager
def session_scope() -> Generator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def login_user(username: str, password: str) -> tuple[Any, ...]:
    return _authenticate(username, password, register=False)


def register_user(username: str, password: str) -> tuple[Any, ...]:
    return _authenticate(username, password, register=True)


def _authenticate(username: str, password: str, register: bool) -> tuple[Any, ...]:
    try:
        with session_scope() as db:
            auth = AuthService(db)
            user, token = (
                auth.register(username, password)
                if register
                else auth.login(username, password)
            )
            choices = _job_choices(
                JobService(db, get_storage_paths()).list_jobs(user.user_id)
            )
        selected = choices[0][1] if choices else None
        action = "注册并登录" if register else "登录"
        return (
            f"{action}成功。",
            token,
            f"当前账号：**{user.username}**",
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(choices=choices, value=selected),
            selected,
        )
    except AppError as exc:
        return (
            exc.message,
            None,
            "",
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(choices=[], value=None),
            None,
        )
    except Exception as exc:
        return (
            f"登录失败：{exc}",
            None,
            "",
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(choices=[], value=None),
            None,
        )


def logout_user(token: str | None) -> tuple[Any, ...]:
    if token:
        with session_scope() as db:
            AuthService(db).logout(token)
    return (
        "已退出登录。后台任务不会停止。",
        None,
        "",
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(choices=[], value=None),
        None,
    )


def create_job(
    token: str | None,
    file_path: str | None,
    mode: str,
    ocr_mode: str = "auto",
    target_language: str = "zh",
    require_high_risk_review: bool = False,
    require_chapter_review: bool = False,
) -> tuple[str, Any, str | None]:
    if not file_path:
        return "请先选择 PDF、Markdown 或 TXT 文件。", gr.update(), None
    source = Path(file_path)
    try:
        with session_scope() as db:
            user = _user(db, token)
            service = JobService(db, get_storage_paths())
            job = service.create_job_from_path(
                source,
                source.name,
                mode,
                ocr_mode,
                require_high_risk_review,
                require_chapter_review,
                target_language=target_language,
                user_id=user.user_id,
            )
            get_worker().enqueue(job.job_id)
            choices = _job_choices(service.list_jobs(user.user_id))
            return (
                f"任务“{job.original_filename}”已进入后台队列。关闭页面不会停止处理。",
                gr.update(choices=choices, value=job.job_id),
                job.job_id,
            )
    except AppError as exc:
        return exc.message, gr.update(), None
    except Exception as exc:
        return f"创建任务失败：{exc}", gr.update(), None


def list_job_choices(token: str | None) -> tuple[Any, str | None]:
    try:
        with session_scope() as db:
            user = _user(db, token)
            choices = _job_choices(
                JobService(db, get_storage_paths()).list_jobs(user.user_id)
            )
        value = choices[0][1] if choices else None
        return gr.update(choices=choices, value=value), value
    except AppError:
        return gr.update(choices=[], value=None), None


def select_job(job_id: str | None) -> str | None:
    return job_id


def cancel_job(token: str | None, job_id: str | None) -> str:
    if not job_id:
        return "请先选择任务。"
    try:
        with session_scope() as db:
            user = _user(db, token)
            job = JobService(db, get_storage_paths()).cancel_job(job_id, user.user_id)
            return f"任务已更新为“{STATUS_LABELS.get(job.status, job.status)}”。"
    except AppError as exc:
        return exc.message
    except Exception as exc:
        return f"取消任务失败：{exc}"


def resume_job(token: str | None, job_id: str | None) -> str:
    if not job_id:
        return "请先选择任务。"
    try:
        with session_scope() as db:
            user = _user(db, token)
            JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
        get_worker().resume(job_id)
        return "任务已重新入队，将从最近检查点恢复。"
    except AppError as exc:
        return exc.message
    except Exception as exc:
        return f"恢复任务失败：{exc}"


def confirm_terms(token: str | None, job_id: str | None, rows: list[list[Any]]) -> str:
    if not job_id:
        return "请先选择任务。"
    try:
        with session_scope() as db:
            user = _user(db, token)
            JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
            terms = TermService(db).list_terms(job_id)
            by_source = {term.source_term: term for term in terms}
            confirmations = [
                TermConfirmation(
                    term_id=by_source[str(row[0])].term_id,
                    confirmed_translation=str(row[2] or row[1]),
                    note=str(row[3]) if row[3] else None,
                )
                for row in rows
                if str(row[0]) in by_source
            ]
            TermService(db).confirm(job_id, confirmations)
        get_worker().resume_review(job_id)
        return "术语已确认，后台翻译继续运行。"
    except (AppError, ValueError) as exc:
        return getattr(exc, "message", str(exc))
    except Exception as exc:
        return f"确认术语失败：{exc}"


def approve_pending_review(token: str | None, job_id: str | None, note: str) -> str:
    if not job_id:
        return "请先选择任务。"
    try:
        with session_scope() as db:
            user = _user(db, token)
            JobService(db, get_storage_paths()).get_job(job_id, user.user_id)
            reviews = ReviewService(db).list_reviews(job_id)
            pending = next((item for item in reviews if item.status == "PENDING"), None)
            if pending is None:
                return "当前没有待处理审核。"
            ReviewService(db).approve(job_id, pending.review_id, note or None)
        get_worker().resume_review(
            job_id, {"approved": True, "reviewId": pending.review_id}
        )
        return "当前风险项已接受，工作流继续。"
    except AppError as exc:
        return exc.message
    except Exception as exc:
        return f"审核失败：{exc}"


def ocr_visibility(file_path: str | None) -> Any:
    return gr.update(
        visible=bool(file_path and Path(file_path).suffix.lower() == ".pdf")
    )


def refresh_dashboard(token: str | None, job_id: str | None) -> tuple[Any, ...]:
    empty = ([], [], [], [], [], None, None, None, None, None, None, None)
    if not job_id:
        return ("请选择左侧任务。", *empty)
    try:
        with session_scope() as db:
            user = _user(db, token)
            service = JobService(db, get_storage_paths())
            job = service.get_job(job_id, user.user_id)
            ObjectStorageService(get_storage_paths()).materialize_job(job)
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
            events = EventService(db).list_events(job_id)
            reviews = ReviewService(db).list_reviews(job_id)
            paths = get_storage_paths()
            return (
                _job_html(job, service.queue_position(job_id)),
                [
                    [
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
                        chunk.chunk_index + 1,
                        " / ".join(chunk.section_path or [])
                        or chunk.section_title
                        or "正文",
                        chunk.chunk_type,
                        STATUS_LABELS.get(chunk.status, chunk.status),
                        chunk.token_estimate,
                        "需复核" if chunk.has_risk else "正常",
                    ]
                    for chunk in chunks
                ],
                [_risk_row(risk, chunks) for risk in risks],
                [
                    [
                        event.created_at.strftime("%m-%d %H:%M:%S"),
                        _stage_label(event.node),
                        event.status,
                        _duration(event.elapsed_ms),
                        event.message or "",
                    ]
                    for event in events
                ],
                [
                    [
                        "高风险片段"
                        if review.review_type == "HIGH_RISK_CHUNK"
                        else "章节确认",
                        _review_location(review.payload_json),
                        "待确认" if review.status == "PENDING" else "已通过",
                        review.resolution_note or "",
                    ]
                    for review in reviews
                ],
                _existing_output(paths.output_file(job_id, "bilingual")),
                _existing_output(paths.output_file(job_id, "translated")),
                _existing_output(paths.output_file(job_id, "report")),
                _existing_output(paths.output_file(job_id, "bilingual_html")),
                _existing_output(paths.output_file(job_id, "translated_html")),
                _existing_output(paths.output_file(job_id, "package")),
                _existing_output(Path(job.original_file_path)),
            )
    except AppError as exc:
        return (exc.message, *empty)
    except Exception as exc:
        return (f"刷新失败：{exc}", *empty)


def _user(db: Session, token: str | None):
    if not token:
        raise AppError(ErrorCode.VALIDATION_ERROR, "请先登录", status_code=401)
    return AuthService(db).authenticate(token)


def _job_choices(jobs: list[Any]) -> list[tuple[str, str]]:
    return [
        (
            f"{job.original_filename} · {STATUS_LABELS.get(job.status, job.status)} · {job.progress_percent:.0f}%",
            job.job_id,
        )
        for job in jobs
    ]


def _job_html(job: Any, queue_position: int | None) -> str:
    eta = "正在估算" if job.eta_seconds is None else _duration(job.eta_seconds * 1000)
    queue = f"<span>队列第 {queue_position} 位</span>" if queue_position else ""
    source_language = (job.source_language or "检测中").upper()
    status = escape(STATUS_LABELS.get(job.status, job.status))
    risk = (
        '<div class="job-risk">存在尚未人工复核的风险项，请在“风险”页查看。</div>'
        if job.has_unresolved_risks
        else ""
    )
    error = (
        f'<div class="job-error">失败原因：{escape(job.error_message)}</div>'
        if job.error_message
        else ""
    )
    progress = max(0.0, min(100.0, float(job.progress_percent)))
    return (
        '<section class="job-summary-content">'
        f'<div class="job-title-row"><h2>{escape(job.original_filename)}</h2>'
        f"<strong>{status}</strong></div>"
        '<div class="job-language">'
        f"{source_language} <span>→</span> {escape(job.target_language.upper())}"
        f"{queue}</div>"
        '<div class="job-progress-track">'
        f'<span style="width:{progress:.1f}%"></span></div>'
        '<div class="job-stats">'
        f"<span>进度 <strong>{job.completed_chunks}/{job.total_chunks}</strong></span>"
        f"<span><strong>{progress:.1f}%</strong></span>"
        f"<span>预计剩余 <strong>{escape(eta)}</strong></span>"
        f"<span>阶段 <strong>{escape(_stage_label(job.current_stage))}</strong></span>"
        "</div>"
        f'<div class="job-updated">最后更新 {job.updated_at.strftime("%Y-%m-%d %H:%M:%S")}</div>'
        f"{risk}{error}</section>"
    )


def _risk_row(risk: RiskItem, chunks: list[DocumentChunk]) -> list[str]:
    chunk = next((item for item in chunks if item.chunk_id == risk.chunk_id), None)
    metadata = risk.metadata_json or {}
    page = metadata.get("leftPage") or metadata.get("pageNo")
    location = f"第 {page} 页" if page else "文档级"
    if chunk and chunk.section_path:
        location = f"{' / '.join(chunk.section_path)} · {location}"
    return [
        risk.severity,
        RISK_LABELS.get(risk.risk_type, risk.risk_type),
        location,
        risk.message,
        (risk.source_excerpt or "")[:300],
        str(metadata.get("systemAction", "已保留原文和结构证据")),
        str(metadata.get("suggestedAction", "建议对照原文复核")),
    ]


def _review_location(payload: dict[str, Any]) -> str:
    path = payload.get("sectionPath") or []
    index = payload.get("chunkIndex")
    if path:
        return " / ".join(path)
    return f"第 {int(index) + 1} 个片段" if isinstance(index, int) else "当前片段"


def _stage_label(stage: str) -> str:
    labels = {
        "uploaded": "等待 Worker",
        "parse_document": "解析文档",
        "detect_language": "检测语言",
        "discover_boundary_candidates": "发现疑似边界",
        "analyze_semantic_boundaries": "语义边界判断",
        "fallback_boundary_analysis": "边界规则降级",
        "normalize_cross_page_text": "修复跨页文本",
        "split_sections": "结构化切分",
        "extract_terms": "抽取术语",
        "interrupt_for_term_review": "等待术语确认",
        "translate_chunk": "翻译片段",
        "mark_risks": "质量与风险检查",
        "summarize_chunk_context": "更新上下文摘要",
        "save_checkpoint": "保存检查点",
        "generate_outputs": "生成输出",
        "validate_outputs": "校验输出",
        "generate_report": "生成报告与结果包",
        "completed": "已完成",
    }
    return labels.get(stage, stage.replace("_", " "))


def _duration(milliseconds: int | None) -> str:
    if milliseconds is None:
        return "-"
    seconds = max(0, int(milliseconds / 1000))
    if seconds < 60:
        return f"{seconds} 秒"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} 分 {seconds} 秒"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} 小时 {minutes} 分"


def _existing_output(path: Path) -> str | None:
    return str(path) if path.is_file() else None
