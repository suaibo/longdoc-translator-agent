from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.job import to_camel


class TermSuggestion(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    source_term: str
    suggested_translation: str
    note: str | None = None

    @field_validator("source_term", "suggested_translation")
    @classmethod
    def non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("term values cannot be empty")
        return value


class TermExtractionResult(BaseModel):
    terms: list[TermSuggestion] = Field(default_factory=list)


class TermResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    term_id: str
    source_term: str
    suggested_translation: str
    confirmed_translation: str | None
    note: str | None
    confirmed: bool


class TermConfirmation(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    term_id: str
    confirmed_translation: str
    note: str | None = None

    @field_validator("confirmed_translation")
    @classmethod
    def confirmed_translation_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("confirmedTranslation cannot be empty")
        return value


class ConfirmTermsRequest(BaseModel):
    terms: list[TermConfirmation] = Field(default_factory=list)
