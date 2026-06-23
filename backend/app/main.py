from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.routes_health import router as health_router
from app.core.errors import (
    AppError,
    app_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging
from app.db.init_db import init_db
from app.db.session import engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    init_db(engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="LongDoc Translator Agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    return app


app = create_app()
