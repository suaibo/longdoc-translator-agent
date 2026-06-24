from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORAGE_ROOT = PROJECT_ROOT / "storage"
DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://longdoc:longdoc@127.0.0.1:5432/longdoc_translator"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = DEFAULT_DATABASE_URL
    database_connect_timeout: int = 5
    storage_root: Path = Field(default=DEFAULT_STORAGE_ROOT)
    max_upload_bytes: int = 50 * 1024 * 1024
    upload_read_size: int = 1024 * 1024
    chunk_max_tokens: int = 1800
    table_max_rows: int = 20

    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-v4-flash"

    ocr_engine: str = "rapidocr-onnxruntime"
    default_ocr_mode: str = "auto"

    @field_validator("storage_root", mode="after")
    @classmethod
    def resolve_storage_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else PROJECT_ROOT / value


@lru_cache
def get_settings() -> Settings:
    return Settings()
