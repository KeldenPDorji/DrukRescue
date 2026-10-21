"""``create_app``: the service template. Every DrukRescue service starts here."""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import DeclarativeBase
from starlette.concurrency import run_in_threadpool

from drukcommon.config import get_settings
from drukcommon.db import Database
from drukcommon.events import EventBus
from drukcommon.logs import setup_logging
from drukcommon.metrics import HTTP_LATENCY, HTTP_REQUESTS, metrics_response, trace_exemplar
from drukcommon.tracing import instrument_engine, instrument_fastapi, setup_tracing

log = logging.getLogger("drukrescue.app")

_QUIET_PATHS = {"/healthz", "/readyz", "/metrics"}


async def _call(fn: Callable) -> None:
    if inspect.iscoroutinefunction(fn):
        await fn()
    else:
        await run_in_threadpool(fn)


def create_app(
    *,
    service: str,
    title: str,
    version: str = "0.1.0",
    database: Database | None = None,
    models_base: type[DeclarativeBase] | None = None,
    bus: EventBus | None = None,
    on_startup: list[Callable] | None = None,
    on_shutdown: list[Callable] | None = None,
    readiness_checks: dict[str, Callable[[], bool]] | None = None,
) -> FastAPI:
    settings = get_settings()
    setup_logging(service, settings.log_level)
    setup_tracing(service, settings.environment)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if database is not None and models_base is not None:
            await run_in_threadpool(database.create_all, models_base)
        for fn in on_startup or []:
            await _call(fn)
        if bus is not None:
            bus.start()
        log.info("service started", extra={"version": version, "environment": settings.environment})
        yield
        if bus is not None:
            bus.stop()
        for fn in on_shutdown or []:
            await _call(fn)
        log.info("service stopped")

    app = FastAPI(title=title, version=version, lifespan=lifespan)

    checks: dict[str, Callable[[], bool]] = {}
    if database is not None:
        checks["database"] = database.ping
    if bus is not None:
        checks["events"] = bus.healthy
    checks.update(readiness_checks or {})

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        """Liveness: the process is up. Never checks dependencies (that would cause restart storms)."""
        return {"status": "ok", "service": service}

    @app.get("/readyz", include_in_schema=False)
    def readyz():
        """Readiness: only receive traffic when our dependencies answer."""
        results: dict[str, str] = {}
        for name, check in checks.items():
            try:
                results[name] = "ok" if check() else "failing"
            except Exception as exc:  # noqa: BLE001 - report, don't crash the probe
                results[name] = f"failing: {type(exc).__name__}"
        ready = all(v == "ok" for v in results.values())
        return JSONResponse({"ready": ready, "checks": results}, status_code=200 if ready else 503)

    @app.get("/metrics", include_in_schema=False)
    def metrics(request: Request):
        return metrics_response(request)

    @app.middleware("http")
    async def observe(request: Request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            elapsed = time.perf_counter() - start
            HTTP_REQUESTS.labels(service, request.method, route_path, str(status)).inc()
            HTTP_LATENCY.labels(service, request.method, route_path).observe(elapsed, exemplar=trace_exemplar())
            if request.url.path not in _QUIET_PATHS:
                log.info(
                    "request",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "route": route_path,
                        "status": status,
                        "duration_ms": round(elapsed * 1000, 1),
                        "user_id": request.headers.get("x-user-id"),
                    },
                )

    instrument_fastapi(app)
    if database is not None:
        instrument_engine(database.engine)
    return app
