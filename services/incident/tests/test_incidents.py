import pytest
from conftest import ADMIN, CITIZEN, FLOOD, OTHER_CITIZEN, RESPONDER

from app.lifecycle import Status, can_transition


def report(client, headers=CITIZEN, **overrides):
    res = client.post("/incidents", json={**FLOOD, **overrides}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def assigned_event(incident_id, **kw):
    return {
        "incident_id": incident_id, "responder_id": 4, "responder_user_id": "resp-user-1",
        "responder_name": "Karma", "team": "Rescue Team 04", "vehicle_id": 7,
        "vehicle_name": "BP-1-A1234", "eta_minutes": 8.5, **kw,
    }


@pytest.mark.parametrize(
    ("current", "target", "ok"),
    [
        (Status.REPORTED, Status.VERIFIED, True),
        (Status.REPORTED, Status.DISPATCHED, False),
        (Status.VERIFIED, Status.DISPATCHED, True),
        (Status.DISPATCHED, Status.IN_PROGRESS, True),
        (Status.IN_PROGRESS, Status.RESOLVED, True),
        (Status.RESOLVED, Status.CANCELLED, False),
        (Status.IN_PROGRESS, Status.CANCELLED, False),
    ],
)
def test_lifecycle_rules(current, target, ok):
    assert can_transition(current, target) is ok


def test_report_creates_incident_and_publishes_event(client, bus):
    inc = report(client)
    assert inc["id"].startswith("INC-") and inc["id"].endswith("-001")
    assert inc["status"] == "REPORTED"
    assert bus.sent("incident.created")[0]["id"] == inc["id"]
    assert bus.sent("dispatch.requests") == []  # nothing goes to Dispatch until verified


def test_validation(client):
    assert client.post("/incidents", json={**FLOOD, "type": "ALIENS"}, headers=CITIZEN).status_code == 422
    assert client.post("/incidents", json={**FLOOD, "photo_url": "javascript:alert(1)"}, headers=CITIZEN).status_code == 422
    assert client.post("/incidents", json=FLOOD).status_code == 401


def test_citizens_only_see_their_own(client):
    mine = report(client)
    report(client, headers=OTHER_CITIZEN)
    assert [i["id"] for i in client.get("/incidents", headers=CITIZEN).json()] == [mine["id"]]
    assert len(client.get("/incidents", headers=ADMIN).json()) == 2
    assert client.get(f"/incidents/{mine['id']}", headers=OTHER_CITIZEN).status_code == 404


def test_full_lifecycle(client, bus):
    inc = report(client)
    code = inc["id"]

    # only admins verify
    assert client.post(f"/incidents/{code}/verify", headers=CITIZEN).status_code == 403
    verified = client.post(f"/incidents/{code}/verify", headers=ADMIN).json()
    assert verified["status"] == "VERIFIED"
    request = bus.sent("dispatch.requests")[0]
    assert request["incident_id"] == code and request["attempt"] == 1

    # Dispatch assigns a team
    bus.deliver("dispatch.assigned", assigned_event(code))
    dispatched = client.get(f"/incidents/{code}", headers=CITIZEN).json()
    assert dispatched["status"] == "DISPATCHED"
    assert dispatched["assigned_team"] == "Rescue Team 04"

    # duplicate delivery is harmless
    bus.deliver("dispatch.assigned", assigned_event(code))
    assert bus.sent("dispatch.release_requested") == []

    # the responder now sees it and moves it along
    assert [i["id"] for i in client.get("/incidents", headers=RESPONDER).json()] == [code]
    assert client.post(f"/incidents/{code}/progress", json={"stage": "RESOLVED"}, headers=RESPONDER).status_code == 409
    for stage, expected in [("EN_ROUTE", "DISPATCHED"), ("ON_SCENE", "IN_PROGRESS"), ("RESOLVED", "RESOLVED")]:
        res = client.post(f"/incidents/{code}/progress", json={"stage": stage}, headers=RESPONDER)
        assert res.status_code == 200, res.text
        assert res.json()["status"] == expected

    stages = [t["stage"] for t in client.get(f"/incidents/{code}/timeline", headers=CITIZEN).json()]
    assert stages[-3:] == ["EN_ROUTE", "ON_SCENE", "RESOLVED"]
    final = bus.sent("incident.status_changed")[-1]
    assert final["status"] == "RESOLVED" and final["assigned_responder_id"] == 4  # Dispatch uses this to free units


def test_other_responders_cannot_update_progress(client, bus):
    code = report(client)["id"]
    client.post(f"/incidents/{code}/verify", headers=ADMIN)
    bus.deliver("dispatch.assigned", assigned_event(code))
    stranger = {"X-User-Id": "resp-user-9", "X-User-Role": "RESPONDER"}
    assert client.post(f"/incidents/{code}/progress", json={"stage": "EN_ROUTE"}, headers=stranger).status_code == 403


def test_assignment_after_cancel_releases_units(client, bus):
    code = report(client)["id"]
    client.post(f"/incidents/{code}/verify", headers=ADMIN)
    client.post(f"/incidents/{code}/cancel", json={"reason": "false alarm"}, headers=ADMIN)
    bus.deliver("dispatch.assigned", assigned_event(code))
    assert client.get(f"/incidents/{code}", headers=ADMIN).json()["status"] == "CANCELLED"
    release = bus.sent("dispatch.release_requested")[0]
    assert release["assigned_responder_id"] == 4 and release["assigned_vehicle_id"] == 7


def test_reporter_can_cancel_only_before_verification(client):
    first = report(client)["id"]
    assert client.post(f"/incidents/{first}/cancel", json={}, headers=CITIZEN).json()["status"] == "CANCELLED"
    second = report(client)["id"]
    client.post(f"/incidents/{second}/verify", headers=ADMIN)
    assert client.post(f"/incidents/{second}/cancel", json={}, headers=CITIZEN).status_code == 403


def test_unassigned_is_recorded_and_redispatch_requeues(client, bus):
    code = report(client)["id"]
    client.post(f"/incidents/{code}/verify", headers=ADMIN)
    bus.deliver("dispatch.unassigned", {"incident_id": code, "reason": "No responder available"})
    assert client.get(f"/incidents/{code}/timeline", headers=ADMIN).json()[-1]["stage"] == "AWAITING_UNITS"
    assert client.post(f"/incidents/{code}/redispatch", headers=ADMIN).status_code == 200
    assert len(bus.sent("dispatch.requests")) == 2


def test_auto_verify(client, bus, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "AUTO_VERIFY", True)
    assert report(client)["status"] == "VERIFIED"
    assert len(bus.sent("dispatch.requests")) == 1


def test_active_metric(client):
    report(client)
    assert 'drukrescue_incidents_active{severity="HIGH"} 1.0' in client.get("/metrics").text
    assert 'drukrescue_incidents_created_total{severity="HIGH",type="FLOOD"}' in client.get("/metrics").text
