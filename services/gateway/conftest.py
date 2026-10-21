import os

os.environ.update({
    "SERVICE_NAME": "gateway",
    "EVENTS_BACKEND": "memory",
    "JWT_SECRET": "test-secret-that-is-at-least-32-characters",
    "RATE_LIMIT_ENABLED": "false",
})

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from drukcommon.auth import Role, create_access_token

SECRET = os.environ["JWT_SECRET"]


def token_for(role: str, user_id: str = "user-1", ttl: int = 5) -> dict:
    tok = create_access_token(user_id=user_id, role=Role(role), name="Test", secret=SECRET, ttl_minutes=ttl)
    return {"Authorization": f"Bearer {tok}"}


def echo(request: httpx.Request) -> httpx.Response:
    """Fake upstream: reports what it received."""
    return httpx.Response(200, json={
        "host": request.url.host,
        "path": request.url.path,
        "query": str(request.url.query, "ascii"),
        "headers": {k.lower(): v for k, v in request.headers.items()},
        "body": json.loads(request.content) if request.content else None,
    })


@pytest.fixture
def client(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "upstream", httpx.AsyncClient(transport=httpx.MockTransport(echo)))
    with TestClient(main.app) as c:
        yield c
