from conftest import ADMIN, CITIZEN, SYSTEM


def make(client, registration="BP-1-A1234", kind="AMBULANCE", **kw):
    res = client.post("/vehicles", json={"registration": registration, "kind": kind, "lat": 27.4, "lng": 89.6, **kw},
                      headers=ADMIN)
    assert res.status_code == 201, res.text
    return res.json()


def test_create_list_filter(client):
    make(client)
    make(client, registration="BP-1-F0001", kind="FIRE_TRUCK")
    res = client.get("/vehicles", params={"status": "AVAILABLE", "kind": "FIRE_TRUCK"}, headers=SYSTEM)
    assert [v["registration"] for v in res.json()] == ["BP-1-F0001"]


def test_duplicate_registration_conflicts(client):
    make(client)
    assert client.post("/vehicles", json={"registration": "BP-1-A1234", "kind": "RESCUE"}, headers=ADMIN).status_code == 409


def test_only_admin_and_system(client):
    assert client.get("/vehicles", headers=CITIZEN).status_code == 403
    assert client.post("/vehicles", json={"registration": "x1", "kind": "RESCUE"}, headers=SYSTEM).status_code == 403


def test_claim_and_release(client):
    v = make(client)
    assert client.post(f"/vehicles/{v['id']}/claim", json={"incident_id": "INC-1"}, headers=SYSTEM).status_code == 200
    assert client.post(f"/vehicles/{v['id']}/claim", json={"incident_id": "INC-2"}, headers=SYSTEM).status_code == 409
    released = client.post(f"/vehicles/{v['id']}/release", json={"incident_id": "INC-1"}, headers=SYSTEM).json()
    assert released["status"] == "AVAILABLE"
