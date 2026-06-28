import json
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode


@dataclass(frozen=True)
class ModelOption:
    id: str
    name: str
    provider: str
    base_url_alias: str = "primary"
    context_window: int | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "baseUrlAlias": self.base_url_alias,
            "contextWindow": self.context_window,
            "description": self.description,
        }


class ModelCatalogService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def list_options(self) -> list[ModelOption]:
        raw = self.settings.llm_model_options_json.strip()
        if not raw:
            default = self.settings.llm_translation_model or self.settings.llm_model
            return [
                ModelOption(
                    id=default,
                    name=default,
                    provider="deepseek",
                    description="服务器默认翻译模型",
                )
            ]
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"LLM_MODEL_OPTIONS_JSON 不是合法 JSON: {exc}",
                status_code=500,
            ) from exc
        if not isinstance(payload, list) or not payload:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "LLM_MODEL_OPTIONS_JSON 必须是非空数组",
                status_code=500,
            )
        options: list[ModelOption] = []
        for item in payload:
            if not isinstance(item, dict):
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    "LLM_MODEL_OPTIONS_JSON 的每一项都必须是对象",
                    status_code=500,
                )
            model_id = str(item.get("id") or "").strip()
            if not model_id:
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    "模型白名单缺少 id",
                    status_code=500,
                )
            options.append(
                ModelOption(
                    id=model_id,
                    name=str(item.get("name") or model_id),
                    provider=str(item.get("provider") or "deepseek"),
                    base_url_alias=str(item.get("baseUrlAlias") or "primary"),
                    context_window=(
                        int(item["contextWindow"])
                        if item.get("contextWindow") is not None
                        else None
                    ),
                    description=str(item.get("description") or ""),
                )
            )
        return options

    def default_model(self) -> str:
        return self.list_options()[0].id

    def validate(self, model_id: str | None) -> str:
        selected = (model_id or self.default_model()).strip()
        allowed = {item.id for item in self.list_options()}
        if selected not in allowed:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "选择的模型不在服务器允许列表中",
                status_code=422,
            )
        return selected
