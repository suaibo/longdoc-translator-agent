from types import SimpleNamespace

from app.schemas.llm import LLMResult, LLMUsage, QualityResult
from app.schemas.term import TermSuggestion


class FakeLLM:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(llm_model="deepseek-test")

    def extract_terms(self, text: str):
        terms = (
            [
                TermSuggestion(
                    source_term="checkpoint",
                    suggested_translation="检查点",
                    note="workflow term",
                )
            ]
            if "checkpoint" in text.casefold()
            else []
        )
        return terms, self.result('{"terms": []}')

    def translate_chunk(
        self,
        source_text: str,
        terms: dict[str, str],
        section_summary: str | None,
        previous_summary: str | None,
        story_memory=None,
        profile: str = "text",
    ) -> LLMResult:
        translated = source_text.replace(
            "checkpoint", terms.get("checkpoint", "检查点")
        )
        return self.result(f"译文：{translated}")

    def summarize_chunk(self, original: str, translated: str) -> LLMResult:
        return self.result("本块介绍检查点和恢复。")

    def check_quality(self, original: str, translated: str):
        return QualityResult(issues=[]), self.result('{"issues": []}')

    def revise_translation(
        self,
        original: str,
        translated: str,
        issues: list[dict[str, str]],
        terms: dict[str, str],
    ) -> LLMResult:
        return self.result(translated)

    def extract_story_memory(self, original: str, translated: str):
        from app.schemas.llm import StoryMemoryResult

        return StoryMemoryResult(entities=[]), self.result('{"entities": []}')

    @staticmethod
    def result(content: str) -> LLMResult:
        return LLMResult(
            content=content,
            usage=LLMUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
            elapsed_ms=20,
        )
