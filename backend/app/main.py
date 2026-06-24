from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import gradio as gr
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse

from app.api.routes_chunks import router as chunks_router
from app.api.routes_events import router as events_router
from app.api.routes_health import router as health_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_outputs import router as outputs_router
from app.api.routes_reviews import router as reviews_router
from app.api.routes_terms import router as terms_router
from app.core.config import get_settings
from app.core.errors import (
    AppError,
    app_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging
from app.db.session import verify_database_connection
from app.services.worker_service import get_worker
from app.ui.gradio_app import create_gradio_app


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    verify_database_connection()
    worker = get_worker() if get_settings().worker_enabled else None
    if worker:
        worker.recover()
    try:
        yield
    finally:
        if worker:
            worker.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title="LongDoc Translator Agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(events_router)
    app.include_router(reviews_router)
    app.include_router(terms_router)
    app.include_router(chunks_router)
    app.include_router(outputs_router)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/ui")

    return gr.mount_gradio_app(app, create_gradio_app(), path="/ui")


app = create_app()
