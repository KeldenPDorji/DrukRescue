import json
import logging
import os

os.environ.setdefault("SERVICE_NAME", "common-test")
os.environ.setdefault("EVENTS_BACKEND", "memory")

import jwt
import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace

from drukcommon import create_app
from drukcommon.auth import Role, create_access_token, decode_access_token
from drukcommon.events import InMemoryEventBus, topic_matches
from drukcommon.logs import JsonFormatter
from drukcommon.tracing import setup_tracing

SECRET = "x" * 40


@pytest.mark.parametrize(
    ("pattern", "key", "expected"),
    [
        ("incident.created", "incident.created", True),
        ("incident.*", "incident.status_changed", True),
        ("incident.*", "incident.a.b", False),
        ("#", "anything.at.all", True),
        ("dispatch.#", "dispatch", True),
        ("*.assigned", "dispatch.assigned", True),
        ("alert.issued", "incident.created", False),
    ],
)
def test_topic_matching(pattern, key, expected):
    assert topic_matches(pattern, key) is expected


def test_jwt_round_trip():
    token = create_access_token(user_id="u1", role=Role.ADMIN, name="Pema", secret=SECRET, ttl_minutes=5)
    claims = decode_access_token(token, SECRET)
    assert claims["sub"] == "u1" and claims["role"] == "ADMIN"


def test_jwt_rejects_wrong_secret_and_expiry():
    token = create_access_token(user_id="u1", role=Role.CITIZEN, name="x", secret=SECRET, ttl_minutes=5)
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token, "y" * 40)
    expired = create_access_token(user_id="u1", role=Role.CITIZEN, name="x", secret=SECRET, ttl_minutes=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired, SECRET)


def test_jwt_secret_must_be_long():
    with pytest.raises(RuntimeError):
        create_access_token(user_id="u", role=Role.ADMIN, name="x", secret="short", ttl_minutes=5)


def test_json_log_has_trace_id():
    setup_tracing("common-test", "test")
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.incident_id = "INC-2026-001"
    with trace.get_tracer("t").start_as_current_span("s"):
        line = json.loads(JsonFormatter("svc").format(record))
    assert line["msg"] == "hello world"
    assert len(line["trace_id"]) == 32
    assert line["incident_id"] == "INC-2026-001"


def test_memory_bus_delivers_to_matching_consumers():
    bus = InMemoryEventBus("t")
    seen = []
    bus.consumer("q1", ["incident.*"])(lambda e: seen.append(("q1", e.type)))
    bus.consumer("q2", ["alert.issued"])(lambda e: seen.append(("q2", e.type)))
    assert bus.deliver("incident.created", {}) == 1
    assert seen == [("q1", "incident.created")]
    bus.publish("incident.created", {"a": 1})
    assert bus.sent("incident.created") == [{"a": 1}]


def test_template_endpoints():
    bus = InMemoryEventBus("t")
    app = create_app(service="common-test", title="t", bus=bus, readiness_checks={"extra": lambda: False})
    with TestClient(app) as client:
        assert client.get("/healthz").json()["status"] == "ok"
        ready = client.get("/readyz")
        assert ready.status_code == 503
        assert ready.json()["checks"] == {"events": "ok", "extra": "failing"}
        body = client.get("/metrics").text
        assert "http_requests_total" in body
