from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.translation_job import TranslationJob
from app.models.translation_metric import TranslationMetric
from app.services.budget_service import BudgetService
from app.services.event_service import EventService


def _job(job_id: str) -> TranslationJob:
    now = datetime.now(timezone.utc)
    return TranslationJob(
        job_id=job_id,
        original_filename="paper.md",
        original_file_path=f"storage/uploads/{job_id}/paper.md",
        mode="paper",
        status="COMPLETED",
        current_stage="completed",
        created_at=now,
        updated_at=now,
    )


def test_event_service_returns_timeline_in_order(db_session: Session) -> None:
    job = _job("job_event_order")
    db_session.add(job)
    db_session.commit()
    service = EventService(db_session)
    first = service.record(job.job_id, "parse_document", "NODE", "STARTED")
    second = service.record(job.job_id, "parse_document", "NODE", "COMPLETED")
    first.created_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    events = service.list_events(job.job_id)

    assert [event.event_id for event in events] == [first.event_id, second.event_id]


@pytest.mark.parametrize(
    ("max_tokens", "max_cost", "tokens", "cost"),
    [
        (100, 0, 100, 0),
        (0, 0.5, 0, 0.5),
    ],
)
def test_budget_service_rejects_exhausted_budget(
    db_session: Session,
    max_tokens: int,
    max_cost: float,
    tokens: int,
    cost: float,
) -> None:
    job = _job(f"job_budget_{max_tokens}_{max_cost}")
    job.max_token_budget = max_tokens
    job.max_cost_usd = max_cost
    db_session.add(job)
    db_session.flush()
    db_session.add(
        TranslationMetric(
            metric_id=f"metric_{job.job_id}",
            job_id=job.job_id,
            provider="deepseek",
            model="deepseek-chat",
            total_tokens=tokens,
            estimated_cost_usd=cost,
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    with pytest.raises(AppError) as error:
        BudgetService(db_session).assert_available(job.job_id)

    assert error.value.status_code == 429


def test_zero_budget_limits_are_disabled(db_session: Session) -> None:
    job = _job("job_budget_disabled")
    job.max_token_budget = 0
    job.max_cost_usd = 0
    db_session.add(job)
    db_session.commit()

    BudgetService(db_session).assert_available(job.job_id)
