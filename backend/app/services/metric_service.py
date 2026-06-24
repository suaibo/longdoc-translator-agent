from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.translation_metric import TranslationMetric
from app.schemas.llm import LLMResult


class MetricService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        job_id: str,
        result: LLMResult,
        *,
        chunk_id: str | None = None,
        provider: str = "deepseek",
        model: str | None = None,
        failed_count: int = 0,
    ) -> TranslationMetric:
        metric = TranslationMetric(
            metric_id=f"metric_{uuid4().hex}",
            job_id=job_id,
            chunk_id=chunk_id,
            provider=provider,
            model=model,
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
            elapsed_ms=result.elapsed_ms,
            retry_count=result.retry_count,
            failed_count=failed_count,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(metric)
        self.db.flush()
        return metric
