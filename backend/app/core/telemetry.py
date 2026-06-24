from contextlib import contextmanager
from typing import Any

from opentelemetry import trace

from app.core.config import get_settings

_configured = False


def configure_telemetry() -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()
    if settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create(
                {"service.name": settings.otel_service_name}
            )
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=settings.otel_exporter_otlp_endpoint
                )
            )
        )
        trace.set_tracer_provider(provider)
    _configured = True


@contextmanager
def span(name: str, **attributes: Any):
    tracer = trace.get_tracer("longdoc-translator-agent")
    with tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value)
        try:
            yield current
        except Exception as exc:
            current.record_exception(exc)
            current.set_status(trace.Status(trace.StatusCode.ERROR))
            raise
