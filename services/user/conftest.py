import os

os.environ.update({"SERVICE_NAME": "user", "EVENTS_BACKEND": "memory", "DATABASE_URL": "sqlite://"})

import pytest
from fastapi.testclient import TestClient

SYSTEM = {"X-User-Id": "system:auth", "X-User-Role": "SYSTEM"}
ADMIN = {"X-User-Id": "admin-1", "X-User-Role": "ADMIN"}


@pytest.fixture
def client():
    from app.main import app, database
    from app.models import Base

    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(database.engine)
