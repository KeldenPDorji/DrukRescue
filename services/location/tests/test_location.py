import pytest
from fastapi.testclient import TestClient

from app.geo import haversine_km
from app.main import app

THIMPHU = (27.4728, 89.6390)
PARO = (27.4305, 89.4133)
PHUENTSHOLING = (26.8516, 89.3884)


def test_haversine_known_distance():
    # Thimphu <-> Paro is roughly 22 km in a straight line.
    assert haversine_km(*THIMPHU, *PARO) == pytest.approx(22.7, abs=1.0)
    assert haversine_km(*THIMPHU, *THIMPHU) == 0


def test_nearest_sorts_and_skips_units_without_coordinates():
    client = TestClient(app)
    res = client.post(
        "/location/nearest",
        json={
            "origin": {"lat": THIMPHU[0], "lng": THIMPHU[1]},
            "units": [
                {"id": 1, "lat": PHUENTSHOLING[0], "lng": PHUENTSHOLING[1], "name": "far"},
                {"id": 2, "lat": PARO[0], "lng": PARO[1], "name": "near"},
                {"id": 3, "name": "no gps"},
            ],
        },
    )
    assert res.status_code == 200
    results = res.json()["results"]
    assert [r["id"] for r in results] == [2, 1]
    assert results[0]["name"] == "near"
    assert results[0]["eta_minutes"] > 0


def test_nearest_limit_and_validation():
    client = TestClient(app)
    body = {"origin": {"lat": 27.0, "lng": 89.0}, "units": [{"id": i, "lat": 27 + i / 100, "lng": 89} for i in range(5)]}
    assert len(client.post("/location/nearest", json={**body, "limit": 2}).json()["results"]) == 2
    assert client.post("/location/nearest", json={"origin": {"lat": 200, "lng": 0}, "units": []}).status_code == 422
