from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.models.translation_job import TranslationJob
from app.models.translation_metric import TranslationMetric


class BudgetService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def assert_available(self, job_id: str) -> None:
        job = self.db.get(TranslationJob, job_id)
        if job is None:
            raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)
        totals = self.db.execute(
            select(
                func.coalesce(func.sum(TranslationMetric.total_tokens), 0),
                func.coalesce(func.sum(TranslationMetric.estimated_cost_usd), 0),
            ).where(TranslationMetric.job_id == job_id)
        ).one()
        tokens, cost = int(totals[0]), float(totals[1])
        if job.max_token_budget > 0 and tokens >= job.max_token_budget:
            raise AppError(
                ErrorCode.LLM_CALL_FAILED,
                f"任务 token 预算已耗尽：{tokens}/{job.max_token_budget}",
                status_code=429,
            )
        if job.max_cost_usd > 0 and cost >= job.max_cost_usd:
            raise AppError(
                ErrorCode.LLM_CALL_FAILED,
                f"任务费用预算已耗尽：${cost:.6f}/${job.max_cost_usd:.6f}",
                status_code=429,
            )
