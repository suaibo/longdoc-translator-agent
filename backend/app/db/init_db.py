from pathlib import Path

from sqlalchemy import Engine, inspect, text

from app.core.config import get_settings
from app.db.base import Base

# Import models so SQLAlchemy registers every table before create_all runs.
from app.models.agent_checkpoint import AgentCheckpoint  # noqa: F401
from app.models.document_chunk import DocumentChunk  # noqa: F401
from app.models.risk_item import RiskItem  # noqa: F401
from app.models.term_entry import TermEntry  # noqa: F401
from app.models.translation_job import TranslationJob  # noqa: F401
from app.models.translation_metric import TranslationMetric  # noqa: F401


def init_db(engine: Engine) -> None:
    settings = get_settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    _ensure_sqlite_parent(settings.database_url)
    Base.metadata.create_all(bind=engine)
    _apply_additive_sqlite_migrations(engine)


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return

    raw_path = database_url.removeprefix("sqlite:///")
    if raw_path == ":memory:":
        return

    Path(raw_path).parent.mkdir(parents=True, exist_ok=True)


def _apply_additive_sqlite_migrations(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    additions = {
        "document_chunk": {
            "chunk_type": "TEXT NOT NULL DEFAULT 'TEXT'",
            "source_block_ids": "TEXT NOT NULL DEFAULT '[]'",
            "structure_metadata": "TEXT NOT NULL DEFAULT '{}'",
        },
        "risk_item": {
            "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        },
    }
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, columns in additions.items():
            if table_name not in inspector.get_table_names():
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, definition in columns.items():
                if column_name in existing:
                    continue
                # Column names and definitions are internal constants, not user input.
                connection.execute(
                    text(
                        f'ALTER TABLE "{table_name}" '
                        f'ADD COLUMN "{column_name}" {definition}'
                    )
                )
