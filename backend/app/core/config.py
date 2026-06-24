from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORAGE_ROOT = PROJECT_ROOT / "storage"
DEFAULT_DATABASE_URL = f"sqlite:///{(DEFAULT_STORAGE_ROOT / 'app.db').as_posix()}"


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
    storage_root: Path = Field(default=DEFAULT_STORAGE_ROOT)
    max_upload_bytes: int = 50 * 1024 * 1024
    upload_read_size: int = 1024 * 1024

    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-v4-flash"

    ocr_engine: str = "docling-default"
    default_ocr_mode: str = "auto"


@lru_cache
def get_settings() -> Settings:
    return Settings()
