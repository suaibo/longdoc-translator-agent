import json
import time
from collections.abc import Callable
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)
from pydantic import ValidationError

from app.agent.prompts import (
    QUALITY_SYSTEM,
    SUMMARY_SYSTEM,
    TERM_EXTRACTION_SYSTEM,
    TRANSLATION_SYSTEM,
)
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.schemas.llm import LLMResult, LLMUsage, QualityResult
from app.schemas.term import TermExtractionResult, TermSuggestion

RETRYABLE_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)


class LLMService:
    def __init__(
        self,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = get_settings()
        if client is None:
            if not self.settings.llm_api_key:
                raise AppError(
                    ErrorCode.LLM_CALL_FAILED,
                    "未配置 LLM_API_KEY，无法调用 DeepSeek",
                    status_code=500,
                )
            client = OpenAI(
                api_key=self.settings.llm_api_key,
                base_url=self.settings.llm_base_url,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=0,
            )
        self.client = client
        self.sleep = sleep

    def extract_terms(self, text: str) -> tuple[list[TermSuggestion], LLMResult]:
        result = self._chat(
            [
                {"role": "system", "content": TERM_EXTRACTION_SYSTEM},
                {"role": "user", "content": text},
            ],
            json_output=True,
        )
        try:
            parsed = TermExtractionResult.model_validate_json(result.content)
        except ValidationError as exc:
            raise AppError(
                ErrorCode.LLM_CALL_FAILED,
                f"DeepSeek 术语 JSON 校验失败: {exc}",
                status_code=502,
            ) from exc
        return parsed.terms, result

    def translate_chunk(
        self,
        source_text: str,
        terms: dict[str, str],
        section_summary: str | None,
        previous_summary: str | None,
    ) -> LLMResult:
        context = {
            "confirmedTerms": terms,
            "sectionSummary": section_summary or "",
            "previousChunkSummary": previous_summary or "",
            "sourceChunk": source_text,
        }
        return self._chat(
            [
                {"role": "system", "content": TRANSLATION_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(context, ensure_ascii=False),
                },
            ]
        )

    def summarize_chunk(self, original: str, translated: str) -> LLMResult:
        return self._chat(
            [
                {"role": "system", "content": SUMMARY_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"original": original, "translated": translated},
                        ensure_ascii=False,
                    ),
                },
            ]
        )

    def check_quality(self, original: str, translated: str) -> tuple[QualityResult, LLMResult]:
        result = self._chat(
            [
                {"role": "system", "content": QUALITY_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"source": original, "translation": translated},
                        ensure_ascii=False,
                    ),
                },
            ],
            json_output=True,
        )
        try:
            return QualityResult.model_validate_json(result.content), result
        except ValidationError as exc:
            raise AppError(
                ErrorCode.LLM_CALL_FAILED,
                f"DeepSeek 质量检查 JSON 校验失败: {exc}",
                status_code=502,
            ) from exc

    def _chat(
        self, messages: list[dict[str, str]], json_output: bool = False
    ) -> LLMResult:
        last_error: Exception | None = None
        started = time.perf_counter()
        for attempt in range(self.settings.llm_max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.settings.llm_model,
                    messages=messages,
                    max_tokens=self.settings.llm_max_output_tokens,
                    response_format={"type": "json_object"} if json_output else None,
                )
                content = response.choices[0].message.content or ""
                if not content.strip():
                    raise ValueError("DeepSeek returned empty content")
                usage = getattr(response, "usage", None)
                return LLMResult(
                    content=content.strip(),
                    usage=LLMUsage(
                        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                        total_tokens=getattr(usage, "total_tokens", 0) or 0,
                    ),
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                    retry_count=attempt,
                )
            except RETRYABLE_ERRORS as exc:
                last_error = exc
                if attempt >= self.settings.llm_max_retries:
                    break
                self.sleep(self.settings.llm_retry_base_seconds * (2**attempt))
            except (BadRequestError, APIError, ValueError) as exc:
                last_error = exc
                break

        raise AppError(
            ErrorCode.LLM_CALL_FAILED,
            f"DeepSeek 调用失败: {last_error}",
            status_code=502,
        ) from last_error
