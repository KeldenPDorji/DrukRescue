from app.main import on_event
from drukcommon.events import Event

ADMIN = {"X-User-Id": "admin-1", "X-User-Role": "ADMIN"}
CITIZEN = {"X-User-Id": "citizen-1", "X-User-Role": "CITIZEN"}

INCIDENT_CREATED = {
    "id": "INC-2026-001", "type": "FLOOD", "severity": "HIGH",
    "reporter_id": "citizen-1", "district": "Thimphu", "location_name": "Babesa",
}

STATUS_CHANGED = {
    **INCIDENT_CREATED, "status": "VERIFIED", "from_status": "REPORTED",
    "actor_id": "admin-1", "incident_id": "INC-2026-001",
}

DISPATCH_ASSIGNED = {
    "incident_id": "INC-2026-001", "incident_type": "FLOOD", "severity": "HIGH",
    "district": "Thimphu", "responder_id": 4, "responder_name": "Team 04",
    "vehicle_id": 7, "vehicle_name": "BP-1-R0001",
}

ALERT_ISSUED = {
    "alert_id": 1, "title": "Flash flood warning", "message": "Move to higher ground",
    "district": "Thimphu", "severity": "CRITICAL", "issued_by": "admin-1",
}


def test_service_boots(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").status_code == 200
    assert "http_requests_total" in client.get("/metrics").text


def test_event_stored(client, bus):
    bus.deliver("incident.created", INCIDENT_CREATED)
    entries = client.get("/audit", headers=ADMIN).json()
    assert len(entries) == 1
    assert entries[0]["event_type"] == "incident.created"
    assert entries[0]["source"] == "test"
    assert entries[0]["entity_id"] == "INC-2026-001"
    assert entries[0]["actor_id"] == "citizen-1"
    assert entries[0]["payload"]["type"] == "FLOOD"


def test_multiple_event_types(client, bus):
    bus.deliver("incident.created", INCIDENT_CREATED)
    bus.deliver("incident.status_changed", STATUS_CHANGED)
    bus.deliver("dispatch.assigned", DISPATCH_ASSIGNED)
    bus.deliver("alert.issued", ALERT_ISSUED)
    entries = client.get("/audit", headers=ADMIN).json()
    assert len(entries) == 4
    types = {e["event_type"] for e in entries}
    assert types == {"incident.created", "incident.status_changed", "dispatch.assigned", "alert.issued"}


def test_actor_extraction(client, bus):
    bus.deliver("incident.status_changed", STATUS_CHANGED)
    entries = client.get("/audit", headers=ADMIN).json()
    assert entries[0]["actor_id"] == "admin-1"


def test_actor_from_issued_by(client, bus):
    bus.deliver("alert.issued", ALERT_ISSUED)
    entries = client.get("/audit", headers=ADMIN).json()
    assert entries[0]["actor_id"] == "admin-1"


def test_entity_extraction_alert(client, bus):
    bus.deliver("alert.issued", ALERT_ISSUED)
    entries = client.get("/audit", headers=ADMIN).json()
    assert entries[0]["entity_id"] == "1"


def test_duplicate_event_ignored(client, bus):
    event = Event(type="incident.created", data=INCIDENT_CREATED, source="incident")
    on_event(event)
    on_event(event)
    entries = client.get("/audit", headers=ADMIN).json()
    assert len(entries) == 1


def test_filter_by_event_type(client, bus):
    bus.deliver("incident.created", INCIDENT_CREATED)
    bus.deliver("alert.issued", ALERT_ISSUED)
    entries = client.get("/audit?event_type=alert.issued", headers=ADMIN).json()
    assert len(entries) == 1
    assert entries[0]["event_type"] == "alert.issued"


def test_filter_by_entity_id(client, bus):
    bus.deliver("incident.created", INCIDENT_CREATED)
    bus.deliver("dispatch.assigned", DISPATCH_ASSIGNED)
    entries = client.get("/audit?entity_id=INC-2026-001", headers=ADMIN).json()
    assert len(entries) == 2


def test_filter_by_actor_id(client, bus):
    bus.deliver("incident.created", INCIDENT_CREATED)
    bus.deliver("incident.status_changed", STATUS_CHANGED)
    entries = client.get("/audit?actor_id=admin-1", headers=ADMIN).json()
    assert len(entries) == 1
    assert entries[0]["event_type"] == "incident.status_changed"


def test_limit(client, bus):
    bus.deliver("incident.created", INCIDENT_CREATED)
    bus.deliver("alert.issued", ALERT_ISSUED)
    entries = client.get("/audit?limit=1", headers=ADMIN).json()
    assert len(entries) == 1


def test_newest_first(client, bus):
    bus.deliver("incident.created", INCIDENT_CREATED)
    bus.deliver("alert.issued", ALERT_ISSUED)
    entries = client.get("/audit", headers=ADMIN).json()
    assert entries[0]["event_type"] == "alert.issued"
    assert entries[1]["event_type"] == "incident.created"


def test_citizen_forbidden(client, bus):
    bus.deliver("incident.created", INCIDENT_CREATED)
    resp = client.get("/audit", headers=CITIZEN)
    assert resp.status_code == 403


def test_verify_empty(client):
    result = client.get("/audit/verify", headers=ADMIN).json()
    assert result == {"ok": True, "checked": 0}


def test_verify_chain_intact(client, bus):
    bus.deliver("incident.created", INCIDENT_CREATED)
    bus.deliver("incident.status_changed", STATUS_CHANGED)
    bus.deliver("dispatch.assigned", DISPATCH_ASSIGNED)
    result = client.get("/audit/verify", headers=ADMIN).json()
    assert result["ok"] is True
    assert result["checked"] == 3


def test_verify_detects_tampering(client, bus):
    bus.deliver("incident.created", INCIDENT_CREATED)
    bus.deliver("alert.issued", ALERT_ISSUED)
    from sqlalchemy import select as sa_select

    from app.main import database
    from app.models import AuditEntry
    with database.session() as db:
        entry = db.scalar(sa_select(AuditEntry).order_by(AuditEntry.id).limit(1))
        entry.payload = '{"tampered": true}'
        db.commit()
    result = client.get("/audit/verify", headers=ADMIN).json()
    assert result["ok"] is False
    assert "broken_at" in result


def test_verify_citizen_forbidden(client):
    resp = client.get("/audit/verify", headers=CITIZEN)
    assert resp.status_code == 403
