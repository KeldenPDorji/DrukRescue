import os

os.environ.update({"SERVICE_NAME": "incident", "EVENTS_BACKEND": "memory", "DATABASE_URL": "sqlite://"})

import pytest
from fastapi.testclient import TestClient

ADMIN = {"X-User-Id": "admin-1", "X-User-Role": "ADMIN"}
CITIZEN = {"X-User-Id": "citizen-1", "X-User-Role": "CITIZEN"}
OTHER_CITIZEN = {"X-User-Id": "citizen-2", "X-User-Role": "CITIZEN"}
RESPONDER = {"X-User-Id": "resp-user-1", "X-User-Role": "RESPONDER"}

FLOOD = {
    "type": "FLOOD",
    "severity": "HIGH",
    "description": "River overflowing near Babesa bridge",
    "lat": 27.4447,
    "lng": 89.6476,
    "district": "Thimphu",
    "location_name": "Babesa",
}


@pytest.fixture
def bus():
    from app.main import bus

    bus.clear()
    return bus


@pytest.fixture
def client(bus):
    from app.main import app, database
    from app.models import Base

    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(database.engine)
