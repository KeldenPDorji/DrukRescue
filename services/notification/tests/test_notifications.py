from app.main import on_event
from drukcommon.events import Event

CITIZEN = {"X-User-Id": "citizen-1", "X-User-Role": "CITIZEN"}
ADMIN = {"X-User-Id": "admin-1", "X-User-Role": "ADMIN"}
RESPONDER = {"X-User-Id": "resp-user-1", "X-User-Role": "RESPONDER"}

INCIDENT = {"id": "INC-2026-001", "type": "FLOOD", "severity": "HIGH", "reporter_id": "citizen-1",
            "district": "Thimphu", "location_name": "Babesa"}


def titles(client, headers):
    return [n["title"] for n in client.get("/notifications/me", headers=headers).json()]


def test_report_notifies_reporter_and_admins(client, bus):
    bus.deliver("incident.created", INCIDENT)
    assert titles(client, CITIZEN) == ["Report received"]
    assert titles(client, ADMIN) == ["New Flood report"]
    assert titles(client, RESPONDER) == []


def test_dispatch_notifies_citizen_and_responder(client, bus):
    bus.deliver("dispatch.assigned", {"incident_id": "INC-2026-001", "reporter_id": "citizen-1",
                                      "responder_user_id": "resp-user-1", "team": "Rescue Team 04",
                                      "vehicle_name": "BP-1-A1234", "eta_minutes": 8.4, "incident_type": "FLOOD"})
    citizen = client.get("/notifications/me", headers=CITIZEN).json()[0]
    assert citizen["title"] == "Rescue team dispatched"
    assert "Rescue Team 04" in citizen["message"] and "ETA about 8 min" in citizen["message"]
    assert titles(client, RESPONDER) == ["New assignment"]


def test_status_changes(client, bus):
    bus.deliver("incident.status_changed", {**INCIDENT, "status": "DISPATCHED", "from_status": "VERIFIED"})
    assert titles(client, CITIZEN) == []  # covered by dispatch.assigned
    bus.deliver("incident.status_changed", {**INCIDENT, "status": "DISPATCHED", "from_status": "DISPATCHED", "stage": "EN_ROUTE"})
    bus.deliver("incident.status_changed", {**INCIDENT, "status": "RESOLVED", "from_status": "IN_PROGRESS", "stage": "RESOLVED"})
    messages = [n["message"] for n in client.get("/notifications/me", headers=CITIZEN).json()]
    assert messages[0].endswith("has been resolved. Stay safe.")
    assert messages[1] == "The rescue team is on the way."


def test_alerts_reach_everyone(client, bus):
    bus.deliver("alert.issued", {"title": "Flash flood warning", "message": "Move to higher ground", "district": "Thimphu",
                                 "severity": "CRITICAL"})
    for who in (CITIZEN, ADMIN, RESPONDER):
        assert titles(client, who) == ["Flash flood warning (Thimphu)"]


def test_duplicate_delivery_is_ignored_and_mark_read(client):
    event = Event(type="incident.created", data=INCIDENT, source="incident")
    on_event(event)
    on_event(event)
    mine = client.get("/notifications/me", headers=CITIZEN).json()
    assert len(mine) == 1
    assert client.post(f"/notifications/{mine[0]['id']}/read", headers=CITIZEN).json()["read"] is True
    assert client.post(f"/notifications/{mine[0]['id']}/read", headers=ADMIN).status_code == 404
