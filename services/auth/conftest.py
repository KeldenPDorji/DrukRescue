import os

os.environ.update({
    "SERVICE_NAME": "auth",
    "EVENTS_BACKEND": "memory",
    "DATABASE_URL": "sqlite://",
    "JWT_SECRET": "test-secret-that-is-at-least-32-characters",
    "BOOTSTRAP_ADMIN_EMAIL": "admin@drukrescue.bt",
    "BOOTSTRAP_ADMIN_PASSWORD": "admin-password-123",
})

import httpx
import pytest
from fastapi.testclient import TestClient


class FakeUserService:
    """Stands in for the User service over HTTP."""

    def __init__(self):
        self.profiles: dict[str, dict] = {}
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down")
        import json

        body = json.loads(request.content)
        if any(p["email"] == body["email"] for p in self.profiles.values()):
            return httpx.Response(409)
        self.profiles[body["id"]] = body
        return httpx.Response(201, json=body)


@pytest.fixture
def users(monkeypatch):
    fake = FakeUserService()
    import app.main as main

    transport = httpx.MockTransport(fake.handler)
    monkeypatch.setattr(main, "user_client", lambda: httpx.Client(base_url="http://user", transport=transport))
    return fake


@pytest.fixture
def client(users):
    from app.main import app, database
    from app.models import Base

    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(database.engine)
