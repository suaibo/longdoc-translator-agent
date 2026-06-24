import json
import time
from collections.abc import Callable
from dataclasses import dataclass
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
    REVISION_SYSTEM,
    STORY_MEMORY_SYSTEM,
    SUMMARY_SYSTEM,
    TERM_EXTRACTION_SYSTEM,
    TRANSLATION_SYSTEM,
)
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.telemetry import span
from app.schemas.llm import (
    LLMResult,
    LLMUsage,
    QualityResult,
    StoryMemoryResult,
)
from app.schemas.term import TermExtractionResult, TermSuggestion

RETRYABLE_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)


@dataclass(frozen=True)
class LLMEndpoint:
    provider: str
    client: Any
    default_model: str


class LLMService:
    def __init__(
        self,
        client: Any | None = None,
        fallback_client: Any | None = None,
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
            client = self._client(
                self.settings.llm_api_key,
                self.settings.llm_base_url,
            )
        self.client = client
        self.endpoints = [
            LLMEndpoint("deepseek", client, self.settings.llm_model)
        ]
        if fallback_client is not None:
            self.endpoints.append(
                LLMEndpoint(
                    "fallback",
                    fallback_client,
                    self.settings.llm_fallback_model or self.settings.llm_model,
                )
            )
        elif (
            self.settings.llm_fallback_api_key
            and self.settings.llm_fallback_base_url
        ):
            self.endpoints.append(
                LLMEndpoint(
                    "fallback",
                    self._client(
                        self.settings.llm_fallback_api_key,
                        self.settings.llm_fallback_base_url,
                    ),
                    self.settings.llm_fallback_model or self.settings.llm_model,
                )
            )
        self.sleep = sleep

    def extract_terms(self, text: str) -> tuple[list[TermSuggestion], LLMResult]:
        result = self._chat(
            [
                {"role": "system", "content": TERM_EXTRACTION_SYSTEM},
                {"role": "user", "content": text},
            ],
            json_output=True,
            task="terms",
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
        story_memory: dict[str, Any] | None = None,
        profile: str = "text",
    ) -> LLMResult:
        context = {
            "confirmedTerms": terms,
            "sectionSummary": section_summary or "",
            "previousChunkSummary": previous_summary or "",
            "sourceChunk": source_text,
            "storyMemory": story_memory or {},
            "translationProfile": profile,
        }
        return self._chat(
            [
                {"role": "system", "content": TRANSLATION_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(context, ensure_ascii=False),
                },
            ]
            ,
            task="translation",
        )

    def extract_story_memory(
        self, original: str, translated: str
    ) -> tuple[StoryMemoryResult, LLMResult]:
        result = self._chat(
            [
                {"role": "system", "content": STORY_MEMORY_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"source": original, "translation": translated},
                        ensure_ascii=False,
                    ),
                },
            ],
            json_output=True,
            task="summary",
        )
        try:
            return StoryMemoryResult.model_validate_json(result.content), result
        except ValidationError as exc:
            raise AppError(
                ErrorCode.LLM_CALL_FAILED,
                f"故事记忆 JSON 校验失败: {exc}",
                status_code=502,
            ) from exc

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
            ,
            task="summary",
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
            task="quality",
        )
        try:
            return QualityResult.model_validate_json(result.content), result
        except ValidationError as exc:
            raise AppError(
                ErrorCode.LLM_CALL_FAILED,
                f"DeepSeek 质量检查 JSON 校验失败: {exc}",
                status_code=502,
            ) from exc

    def revise_translation(
        self,
        original: str,
        translated: str,
        issues: list[dict[str, str]],
        terms: dict[str, str],
    ) -> LLMResult:
        return self._chat(
            [
                {"role": "system", "content": REVISION_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "source": original,
                            "translation": translated,
                            "issues": issues,
                            "confirmedTerms": terms,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            task="translation",
        )

    def _chat(
        self,
        messages: list[dict[str, str]],
        json_output: bool = False,
        task: str = "translation",
    ) -> LLMResult:
        last_error: Exception | None = None
        started = time.perf_counter()
        retries = 0
        for endpoint_index, endpoint in enumerate(self.endpoints):
            model = self._model_for(task, endpoint)
            for attempt in range(self.settings.llm_max_retries + 1):
                try:
                    with span(
                        "llm.chat",
                        llm_provider=endpoint.provider,
                        llm_model=model,
                        llm_task=task,
                        llm_attempt=attempt,
                    ):
                        response = endpoint.client.chat.completions.create(
                            model=model,
                            messages=messages,
                            max_tokens=self.settings.llm_max_output_tokens,
                            response_format=(
                                {"type": "json_object"}
                                if json_output
                                else None
                            ),
                        )
                    content = response.choices[0].message.content or ""
                    if not content.strip():
                        raise ValueError("LLM returned empty content")
                    usage = getattr(response, "usage", None)
                    return LLMResult(
                        content=content.strip(),
                        provider=endpoint.provider,
                        model=model,
                        usage=LLMUsage(
                            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                            completion_tokens=getattr(
                                usage, "completion_tokens", 0
                            )
                            or 0,
                            total_tokens=getattr(usage, "total_tokens", 0) or 0,
                        ),
                        elapsed_ms=int((time.perf_counter() - started) * 1000),
                        retry_count=retries,
                    )
                except RETRYABLE_ERRORS as exc:
                    last_error = exc
                    if attempt >= self.settings.llm_max_retries:
                        break
                    retries += 1
                    self.sleep(
                        self.settings.llm_retry_base_seconds * (2**attempt)
                    )
                except (BadRequestError, APIError, ValueError) as exc:
                    last_error = exc
                    # Invalid requests and invalid content are deterministic;
                    # switching providers would hide a prompt/schema defect.
                    endpoint_index = len(self.endpoints)
                    break
            if endpoint_index >= len(self.endpoints):
                break

        raise AppError(
            ErrorCode.LLM_CALL_FAILED,
            f"LLM 调用失败: {last_error}",
            status_code=502,
        ) from last_error

    def _model_for(self, task: str, endpoint: LLMEndpoint) -> str:
        if endpoint.provider == "fallback":
            return endpoint.default_model
        routed = {
            "terms": self.settings.llm_term_model,
            "translation": self.settings.llm_translation_model,
            "summary": self.settings.llm_summary_model,
            "quality": self.settings.llm_quality_model,
        }.get(task, "")
        return routed or endpoint.default_model

    def _client(self, api_key: str, base_url: str) -> OpenAI:
        return OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=self.settings.llm_timeout_seconds,
            max_retries=0,
        )
