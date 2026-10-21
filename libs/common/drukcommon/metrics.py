"""Prometheus metrics shared by every service."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

from opentelemetry import trace
from prometheus_client import REGISTRY, Counter, Histogram
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.exposition import choose_encoder
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger(__name__)

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests handled",
    ["service", "method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["service", "method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def trace_exemplar() -> dict[str, str] | None:
    """Attach the current trace id to a histogram sample, so Grafana can jump metric -> trace."""
    ctx = trace.get_current_span().get_span_context()
    return {"trace_id": format(ctx.trace_id, "032x")} if ctx.is_valid else None


def metrics_response(request: Request) -> Response:
    # OpenMetrics format (which carries exemplars) is served when Prometheus asks for it.
    encoder, content_type = choose_encoder(request.headers.get("accept", ""))
    return Response(encoder(REGISTRY), media_type=content_type)


class _ScrapeTimeGauge:
    """A gauge whose value is computed when Prometheus scrapes, e.g. from a DB count.

    Using the database as the source means every replica reports the same,
    correct number (use max() in Grafana, not sum()).
    """

    def __init__(self, name: str, documentation: str, labels: list[str], fn: Callable[[], Iterable]):
        self.name, self.documentation, self.labels, self.fn = name, documentation, labels, fn

    def describe(self):
        return []

    def collect(self):
        try:
            rows = list(self.fn())
        except Exception:  # never break /metrics because the DB blinked
            log.warning("could not compute gauge %s", self.name, exc_info=True)
            return
        family = GaugeMetricFamily(self.name, self.documentation, labels=self.labels)
        for label_values, value in rows:
            family.add_metric([str(v) for v in label_values], value)
        yield family


def register_scrape_time_gauge(
    name: str, documentation: str, labels: list[str], fn: Callable[[], Iterable[tuple[tuple, float]]]
) -> None:
    """fn returns [((label1, label2, ...), value), ...]."""
    try:
        REGISTRY.register(_ScrapeTimeGauge(name, documentation, labels, fn))
    except ValueError:
        log.debug("gauge %s already registered", name)
