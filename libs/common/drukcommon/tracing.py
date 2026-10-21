"""OpenTelemetry setup. Spans go to Tempo over OTLP/HTTP when OTEL_EXPORTER_OTLP_ENDPOINT is set.

Without an endpoint we still create a tracer provider, so trace ids exist and
appear in logs. That makes local debugging and tests behave the same as the cluster.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_configured = False


def setup_tracing(service: str, environment: str) -> None:
    global _configured
    if _configured:
        return
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": service,
                "service.namespace": "drukrescue",
                "deployment.environment": environment,
            }
        )
    )
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    # Every outgoing httpx call (service -> service) carries the traceparent header.
    HTTPXClientInstrumentor().instrument()
    _configured = True


def instrument_fastapi(app) -> None:
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz,metrics")


def instrument_engine(engine) -> None:
    SQLAlchemyInstrumentor().instrument(engine=engine)


def tracer(name: str = "drukrescue"):
    return trace.get_tracer(name)
