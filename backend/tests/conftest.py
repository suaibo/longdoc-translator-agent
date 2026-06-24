import os
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, get_settings
from app.db.session import get_db
from app.main import create_app
from app.storage.paths import StoragePaths, get_storage_paths

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://longdoc:longdoc@127.0.0.1:5433/longdoc_translator_test",
)


@pytest.fixture(scope="session")
def migrated_engine() -> Generator[Engine]:
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()

    config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
        get_settings.cache_clear()


@pytest.fixture
def db_session(migrated_engine: Engine) -> Generator[Session]:
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session, tmp_path: Path) -> Generator[TestClient]:
    app = create_app()

    @asynccontextmanager
    async def test_lifespan(_app) -> AsyncIterator[None]:
        yield

    app.router.lifespan_context = test_lifespan
    paths = StoragePaths(tmp_path / "storage")

    def override_db() -> Generator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_storage_paths] = lambda: paths
    with TestClient(app) as test_client:
        yield test_client
