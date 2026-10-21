import os

os.environ.update({
    "SERVICE_NAME": "dispatch",
    "EVENTS_BACKEND": "memory",
    "DISPATCH_RETRY_DELAY_SECONDS": "0",
})

import json
import math

import httpx
import pytest


class FakeWorld:
    """In-memory Incident + Responder + Vehicle + Location services behind one httpx MockTransport."""

    def __init__(self):
        self.incidents: dict[str, dict] = {}
        self.responders: dict[int, dict] = {}
        self.vehicles: dict[int, dict] = {}
        self.calls: list[str] = []
        self.fail_service: str | None = None
        self.stale_listing = False  # list units as AVAILABLE even if already claimed (simulates a race)

    def handler(self, request: httpx.Request) -> httpx.Response:
        service, path, method = request.url.host, request.url.path, request.method
        self.calls.append(f"{method} {service}{path}")
        if service == self.fail_service:
            raise httpx.ConnectError("down")
        body = json.loads(request.content) if request.content else {}
        parts = path.strip("/").split("/")

        if service == "incident":
            inc = self.incidents.get(parts[1])
            return httpx.Response(200, json=inc) if inc else httpx.Response(404)

        if service == "location":
            o = body["origin"]
            units = [dict(u, distance_km=round(math.dist((o["lat"], o["lng"]), (u["lat"], u["lng"])) * 111, 3),
                          eta_minutes=1.0) for u in body["units"]]
            return httpx.Response(200, json={"results": sorted(units, key=lambda u: u["distance_km"])})

        store = self.responders if service == "responder" else self.vehicles
        if method == "GET":
            wanted = request.url.params.get("status")
            return httpx.Response(200, json=[u for u in store.values() if self.stale_listing or u["status"] == wanted])
        unit = store.get(int(parts[1]))
        if unit is None:
            return httpx.Response(404)
        if parts[2] == "claim":
            if unit["status"] != "AVAILABLE":
                return httpx.Response(409)
            unit.update(status="BUSY", current_incident_id=body["incident_id"])
        elif parts[2] == "release" and unit.get("current_incident_id") == body.get("incident_id"):
            unit.update(status="AVAILABLE", current_incident_id=None)
        return httpx.Response(200, json=unit)


@pytest.fixture
def world(monkeypatch):
    import app.main as main

    w = FakeWorld()
    transport = httpx.MockTransport(w.handler)
    for name in ("incident", "responder", "vehicle", "location"):
        monkeypatch.setitem(main._clients, name, httpx.Client(base_url=f"http://{name}", transport=transport))
    main.bus.clear()
    return w
