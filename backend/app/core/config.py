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
    worker_enabled: bool = False
    worker_max_concurrency: int = 5
    user_max_concurrent_jobs: int = 5
    database_url: str = DEFAULT_DATABASE_URL
    database_connect_timeout: int = 5
    storage_root: Path = Field(default=DEFAULT_STORAGE_ROOT)
    storage_backend: str = "local"
    s3_endpoint_url: str = ""
    s3_region: str = "auto"
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_presign_seconds: int = 900
    file_retention_days: int = 30
    max_upload_bytes: int = 50 * 1024 * 1024
    upload_read_size: int = 1024 * 1024
    chunk_max_tokens: int = 1800
    chunk_target_tokens: int = 1200
    chunk_soft_max_tokens: int = 1800
    chunk_hard_max_tokens: int = 2400
    chunk_min_tokens: int = 120
    semantic_boundary_threshold: float = 0.58
    boundary_llm_max_retries: int = 2
    table_max_rows: int = 20

    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-v4-flash"
    llm_model_options_json: str = ""
    llm_term_model: str = ""
    llm_translation_model: str = ""
    llm_summary_model: str = ""
    llm_quality_model: str = ""
    llm_boundary_model: str = ""
    llm_timeout_seconds: float = 120
    llm_max_retries: int = 3
    llm_retry_base_seconds: float = 1
    llm_max_output_tokens: int = 8192
    job_max_token_budget: int = 2_000_000
    job_max_cost_usd: float = 0
    llm_input_cost_per_million: float = 0
    llm_output_cost_per_million: float = 0
    llm_fallback_base_url: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_model: str = ""
    max_revision_attempts: int = 1
    otel_service_name: str = "longdoc-translator-agent"
    otel_exporter_otlp_endpoint: str = ""
    replay_include_text: bool = False
    workflow_version: str = "1"
    prompt_version: str = "1"
    workflow_node_timeout_seconds: float = 1800
    stream_token_secret: str = ""
    stream_token_ttl_seconds: int = 600

    ocr_engine: str = "rapidocr-onnxruntime"
    default_ocr_mode: str = "auto"
    docling_artifacts_path: Path | None = None
    docling_page_batch_size: int = 1
    parser_max_concurrency: int = 1
    auth_session_days: int = 30

    @field_validator("storage_root", mode="after")
    @classmethod
    def resolve_storage_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else PROJECT_ROOT / value

    @field_validator("storage_backend")
    @classmethod
    def validate_storage_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"local", "s3"}:
            raise ValueError("STORAGE_BACKEND must be local or s3")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
