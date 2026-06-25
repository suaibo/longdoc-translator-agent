from pydantic import BaseModel, Field


class LLMUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResult(BaseModel):
    content: str
    provider: str = "deepseek"
    model: str | None = None
    usage: LLMUsage = Field(default_factory=LLMUsage)
    elapsed_ms: int = 0
    retry_count: int = 0


class QualityIssue(BaseModel):
    type: str
    message: str
    severity: str = "MEDIUM"


class QualityResult(BaseModel):
    issues: list[QualityIssue] = Field(default_factory=list)


class StoryEntity(BaseModel):
    entity_type: str = Field(alias="entityType")
    source_name: str = Field(alias="sourceName")
    translated_name: str = Field(alias="translatedName")
    note: str | None = None


class StoryMemoryResult(BaseModel):
    entities: list[StoryEntity] = Field(default_factory=list)


class BoundaryDecisionResult(BaseModel):
    decision: str
    confidence: float = 0.0
    reason: str
    sentence_complete: bool = Field(alias="sentenceComplete")
