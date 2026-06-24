from types import SimpleNamespace

import pytest
from openai import APITimeoutError

from app.core.errors import AppError, ErrorCode
from app.services.llm_service import LLMService


class FakeCompletions:
    def __init__(self, responses):
        self.responses = iter(responses)

    def create(self, **kwargs):
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=7, completion_tokens=3, total_tokens=10
        ),
    )


def client(*responses):
    return SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions(responses))
    )


def test_extract_terms_parses_deepseek_json() -> None:
    service = LLMService(
        client=client(
            response(
                '{"terms":[{"sourceTerm":"checkpoint",'
                '"suggestedTranslation":"检查点"}]}'
            )
        )
    )

    terms, result = service.extract_terms("checkpoint")

    assert terms[0].source_term == "checkpoint"
    assert result.usage.total_tokens == 10


def test_retryable_error_uses_exponential_retry(monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("LLM_MAX_RETRIES", "1")
    get_settings.cache_clear()
    sleeps: list[float] = []
    try:
        service = LLMService(
            client=client(APITimeoutError(request=None), response("译文")),
            sleep=sleeps.append,
        )
        result = service.translate_chunk("text", {}, None, None)
    finally:
        get_settings.cache_clear()

    assert result.content == "译文"
    assert result.retry_count == 1
    assert sleeps == [1.0]


def test_invalid_json_maps_to_llm_error() -> None:
    service = LLMService(client=client(response("not json")))

    with pytest.raises(AppError) as caught:
        service.extract_terms("text")

    assert caught.value.code == ErrorCode.LLM_CALL_FAILED
