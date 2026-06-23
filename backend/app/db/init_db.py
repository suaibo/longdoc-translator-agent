from pathlib import Path

from sqlalchemy import Engine

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


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return

    raw_path = database_url.removeprefix("sqlite:///")
    if raw_path == ":memory:":
        return

    Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
