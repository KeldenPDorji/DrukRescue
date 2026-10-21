import os

os.environ.update({"SERVICE_NAME": "weather", "EVENTS_BACKEND": "memory"})

import pytest
from fastapi.testclient import TestClient

CITIZEN = {"X-User-Id": "citizen-1", "X-User-Role": "CITIZEN"}


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c
