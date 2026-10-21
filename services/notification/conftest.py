import os

os.environ.update({"SERVICE_NAME": "notification", "EVENTS_BACKEND": "memory", "DATABASE_URL": "sqlite://"})

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def bus():
    from app.main import bus

    return bus


@pytest.fixture
def client(bus):
    from app.main import app, database
    from app.models import Base

    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(database.engine)
