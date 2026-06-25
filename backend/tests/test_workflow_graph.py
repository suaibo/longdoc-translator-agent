from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.agent.runner import WorkflowRunner
from app.core.config import get_settings
from app.models.translation_job import TranslationJob
from app.services.event_service import EventService
from app.schemas.term import TermConfirmation
from app.services.job_service import JobService
from app.services.review_service import ReviewService
from app.services.term_service import TermService
from app.storage.paths import StoragePaths
from tests.fakes import FakeLLM


def test_langgraph_interrupt_resume_completes_full_workflow(
    migrated_engine: Engine, tmp_path: Path, monkeypatch
) -> None:
    job_id = None
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    paths = StoragePaths(tmp_path / "storage")
    paths.ensure_root()
    source = tmp_path / "paper.md"
    source.write_text(
        "# Paper\n\nA checkpoint restores state after failure.",
        encoding="utf-8",
    )
    monkeypatch.setenv("STORAGE_ROOT", str(paths.root))
    get_settings.cache_clear()

    import app.agent.nodes as node_module
    import app.agent.graph as graph_module
    import app.services.term_service as term_module
    import app.services.translation_service as translation_module

    monkeypatch.setattr(node_module, "SessionLocal", factory)
    monkeypatch.setattr(graph_module, "SessionLocal", factory)
    monkeypatch.setattr(term_module, "LLMService", FakeLLM)
    monkeypatch.setattr(translation_module, "LLMService", FakeLLM)
    try:
        with factory() as db:
            # Remove any active task left by an interrupted local run.
            db.execute(delete(TranslationJob))
            db.commit()
            job = JobService(db, paths).create_job_from_path(
                source,
                source.name,
                "paper",
                "auto",
                require_chapter_review=True,
            )
            job_id = job.job_id

        runner = WorkflowRunner()
        runner.run(job_id)

        with factory() as db:
            waiting = db.get(TranslationJob, job_id)
            assert waiting is not None
            assert waiting.status == "WAITING_TERM_REVIEW"
            terms = TermService(db).list_terms(job_id)
            TermService(db).confirm(
                job_id,
                [
                    TermConfirmation(
                        term_id=term.term_id,
                        confirmed_translation=term.suggested_translation,
                    )
                    for term in terms
                ],
            )

        runner.run(job_id, {"confirmed": True})

        with factory() as db:
            waiting = db.get(TranslationJob, job_id)
            assert waiting is not None
            assert waiting.status == "WAITING_CHAPTER_REVIEW"
            review = ReviewService(db).list_reviews(job_id)[0]
            ReviewService(db).approve(job_id, review.review_id, "integration checked")

        runner.run(job_id, {"approved": True})

        with factory() as db:
            completed = db.get(TranslationJob, job_id)
            assert completed is not None
            assert completed.status == "COMPLETED"
            assert completed.progress_percent == 100
            assert completed.eta_seconds == 0
            assert paths.document_ir(job_id).is_file()
            assert paths.output_file(job_id, "package").is_file()
            events = EventService(db).list_events(job_id)
            assert any(
                event.node == "interrupt_for_term_review"
                and event.status == "INTERRUPTED"
                for event in events
            )
            assert any(
                event.node == "generate_report" and event.status == "COMPLETED"
                for event in events
            )
    finally:
        get_settings.cache_clear()
        if job_id:
            with factory() as db:
                job = db.get(TranslationJob, job_id)
                if job:
                    db.delete(job)
                    db.commit()
