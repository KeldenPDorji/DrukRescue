"""drukcommon: the shared DrukRescue service template.

Every service gets these for free by calling ``create_app``:

- ``GET /healthz`` (liveness) and ``GET /readyz`` (readiness: DB + RabbitMQ)
- ``GET /metrics`` (Prometheus, with trace exemplars)
- OpenTelemetry traces (exported to Tempo when OTEL_EXPORTER_OTLP_ENDPOINT is set)
- JSON logs with ``trace_id`` / ``span_id`` on every line written inside a request
- Config from environment variables
"""

from drukcommon.app import create_app
from drukcommon.auth import Principal, Role, get_principal, require_roles
from drukcommon.config import get_settings
from drukcommon.db import Database
from drukcommon.events import DISPATCH_QUEUE, Event, EventBus, create_event_bus

__all__ = [
    "DISPATCH_QUEUE",
    "Database",
    "Event",
    "EventBus",
    "Principal",
    "Role",
    "create_app",
    "create_event_bus",
    "get_principal",
    "get_settings",
    "require_roles",
]
