from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app import models  # noqa: F401
from app.db.session import get_db
from app.main import create_app
from app.storage.paths import StoragePaths, get_storage_paths


@pytest.fixture
def db_session() -> Generator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


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
