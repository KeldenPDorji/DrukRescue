from conftest import ADMIN, CITIZEN, SYSTEM


def make(client, **kw):
    body = {"name": "Karma", "team": "Rescue Team 04", "lat": 27.44, "lng": 89.64, **kw}
    res = client.post("/responders", json=body, headers=ADMIN)
    assert res.status_code == 201, res.text
    return res.json()


def test_admin_creates_and_lists(client):
    make(client)
    make(client, name="Dorji", lat=None, lng=None)
    res = client.get("/responders", params={"status": "AVAILABLE"}, headers=SYSTEM)
    assert [r["name"] for r in res.json()] == ["Karma", "Dorji"]


def test_citizen_cannot_create_or_list(client):
    assert client.post("/responders", json={"name": "x", "team": "y"}, headers=CITIZEN).status_code == 403
    assert client.get("/responders", headers=CITIZEN).status_code == 403
    assert client.get("/responders").status_code == 401


def test_claim_is_exclusive_and_release_is_idempotent(client):
    r = make(client)
    first = client.post(f"/responders/{r['id']}/claim", json={"incident_id": "INC-2026-001"}, headers=SYSTEM)
    assert first.status_code == 200 and first.json()["status"] == "BUSY"
    second = client.post(f"/responders/{r['id']}/claim", json={"incident_id": "INC-2026-002"}, headers=SYSTEM)
    assert second.status_code == 409

    # releasing for the wrong incident does nothing
    wrong = client.post(f"/responders/{r['id']}/release", json={"incident_id": "INC-2026-999"}, headers=SYSTEM)
    assert wrong.json()["status"] == "BUSY"
    ok = client.post(f"/responders/{r['id']}/release", json={"incident_id": "INC-2026-001"}, headers=SYSTEM)
    assert ok.json()["status"] == "AVAILABLE" and ok.json()["current_incident_id"] is None


def test_claim_unknown_responder_is_404(client):
    assert client.post("/responders/999/claim", json={"incident_id": "x"}, headers=SYSTEM).status_code == 404


def test_responder_manages_own_status_and_location(client):
    r = make(client, user_id="resp-user-1")
    me = {"X-User-Id": "resp-user-1", "X-User-Role": "RESPONDER"}
    assert client.get("/responders/me", headers=me).json()["id"] == r["id"]
    assert client.patch("/responders/me/location", json={"lat": 27.5, "lng": 89.7}, headers=me).json()["lat"] == 27.5
    assert client.patch("/responders/me/status", json={"status": "OFFLINE"}, headers=me).json()["status"] == "OFFLINE"
    assert client.patch("/responders/me/status", json={"status": "BUSY"}, headers=me).status_code == 400

    client.patch("/responders/me/status", json={"status": "AVAILABLE"}, headers=me)
    client.post(f"/responders/{r['id']}/claim", json={"incident_id": "INC-2026-001"}, headers=SYSTEM)
    assert client.patch("/responders/me/status", json={"status": "AVAILABLE"}, headers=me).status_code == 409


def test_units_available_metric(client):
    make(client)
    assert 'drukrescue_units_available{kind="responder"} 1.0' in client.get("/metrics").text
