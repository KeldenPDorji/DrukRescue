import os

os.environ.update({"SERVICE_NAME": "analytics", "EVENTS_BACKEND": "memory", "DATABASE_URL": "sqlite://"})

import pytest
from fastapi.testclient import TestClient

ADMIN = {"X-User-Id": "admin-1", "X-User-Role": "ADMIN"}
CITIZEN = {"X-User-Id": "citizen-1", "X-User-Role": "CITIZEN"}


@pytest.fixture
def client():
    from app.main import app, database
    from app.models import Base

    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(database.engine)
