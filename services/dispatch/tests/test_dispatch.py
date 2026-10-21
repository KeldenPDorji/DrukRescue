from app.main import DISPATCH_QUEUE, bus, prefer_vehicle_kinds

BABESA = (27.4447, 89.6476)


def request(incident_id="INC-2026-001", type_="FLOOD", **kw):
    return {"incident_id": incident_id, "type": type_, "severity": "HIGH", "lat": BABESA[0], "lng": BABESA[1],
            "reporter_id": "citizen-1", "reported_at": "2026-10-21T00:00:00+00:00", "attempt": 1, **kw}


def seed(world, incident_status="VERIFIED"):
    world.incidents["INC-2026-001"] = {"id": "INC-2026-001", "status": incident_status, "created_at": None}
    world.responders = {
        1: {"id": 1, "name": "Far", "team": "Team 01", "user_id": "u1", "status": "AVAILABLE", "lat": 27.0, "lng": 89.0},
        2: {"id": 2, "name": "Near", "team": "Team 04", "user_id": "u2", "status": "AVAILABLE", "lat": 27.445, "lng": 89.648},
    }
    world.vehicles = {
        10: {"id": 10, "registration": "BP-1-A0001", "kind": "AMBULANCE", "status": "AVAILABLE", "lat": 27.4447, "lng": 89.6476},
        11: {"id": 11, "registration": "BP-1-R0001", "kind": "RESCUE", "status": "AVAILABLE", "lat": 27.40, "lng": 89.60},
    }


def test_assigns_nearest_responder_and_best_vehicle(world):
    seed(world)
    bus.deliver("dispatch.requested", request(), queue=DISPATCH_QUEUE)
    assigned = bus.sent("dispatch.assigned")[0]
    assert assigned["responder_id"] == 2  # nearest
    assert assigned["vehicle_id"] == 11  # RESCUE preferred for floods, even though the ambulance is closer
    assert assigned["reporter_id"] == "citizen-1"
    assert assigned["time_to_dispatch_seconds"] > 0
    assert world.responders[2]["status"] == "BUSY" and world.vehicles[11]["status"] == "BUSY"


def test_skips_incidents_that_are_no_longer_verified(world):
    seed(world, incident_status="CANCELLED")
    bus.deliver("dispatch.requested", request(), queue=DISPATCH_QUEUE)
    assert bus.sent("dispatch.assigned") == []
    assert all(r["status"] == "AVAILABLE" for r in world.responders.values())


def test_falls_through_to_next_candidate_when_claim_loses_race(world):
    seed(world)
    # Another Dispatch pod claimed the nearest team after we listed it as available.
    world.responders[2]["status"] = "BUSY"
    world.stale_listing = True
    bus.deliver("dispatch.requested", request(), queue=DISPATCH_QUEUE)
    assert bus.sent("dispatch.assigned")[0]["responder_id"] == 1
    assert "POST responder/responders/2/claim" in world.calls  # tried, got 409, moved on


def test_no_vehicle_releases_responder_and_retries(world):
    seed(world)
    for v in world.vehicles.values():
        v["status"] = "BUSY"
    bus.deliver("dispatch.requested", request(), queue=DISPATCH_QUEUE)
    retry = bus.sent(DISPATCH_QUEUE)[0]
    assert retry["attempt"] == 2
    assert all(r["status"] == "AVAILABLE" for r in world.responders.values())


def test_gives_up_after_max_attempts(world):
    seed(world)
    world.responders.clear()
    bus.deliver("dispatch.requested", request(attempt=3), queue=DISPATCH_QUEUE)
    assert bus.sent(DISPATCH_QUEUE) == []
    assert bus.sent("dispatch.unassigned")[0]["incident_id"] == "INC-2026-001"


def test_dependency_outage_is_retried_not_crashed(world):
    seed(world)
    world.fail_service = "location"
    bus.deliver("dispatch.requested", request(), queue=DISPATCH_QUEUE)
    assert bus.sent(DISPATCH_QUEUE)[0]["attempt"] == 2


def test_release_on_resolution(world):
    seed(world)
    bus.deliver("dispatch.requested", request(), queue=DISPATCH_QUEUE)
    bus.deliver("incident.status_changed", {"id": "INC-2026-001", "status": "IN_PROGRESS",
                                            "assigned_responder_id": 2, "assigned_vehicle_id": 11})
    assert world.responders[2]["status"] == "BUSY"
    bus.deliver("incident.status_changed", {"id": "INC-2026-001", "status": "RESOLVED",
                                            "assigned_responder_id": 2, "assigned_vehicle_id": 11})
    assert world.responders[2]["status"] == "AVAILABLE" and world.vehicles[11]["status"] == "AVAILABLE"


def test_vehicle_preference_is_stable():
    ranked = [{"id": 1, "kind": "POLICE"}, {"id": 2, "kind": "FIRE_TRUCK"}, {"id": 3, "kind": "FIRE_TRUCK"}]
    assert [v["id"] for v in prefer_vehicle_kinds(ranked, "FIRE")] == [2, 3, 1]
    assert [v["id"] for v in prefer_vehicle_kinds(ranked, "OTHER")] == [1, 2, 3]
