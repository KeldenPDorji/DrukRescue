from conftest import ADMIN, SYSTEM


def test_auth_creates_profile_then_user_reads_and_updates_it(client):
    res = client.post("/users", json={"id": "u-1", "name": "Pema", "email": "Pema@Example.bt"}, headers=SYSTEM)
    assert res.status_code == 201
    assert res.json()["email"] == "pema@example.bt"

    me = {"X-User-Id": "u-1", "X-User-Role": "CITIZEN"}
    assert client.get("/users/me", headers=me).json()["name"] == "Pema"
    assert client.patch("/users/me", json={"district": "Thimphu"}, headers=me).json()["district"] == "Thimphu"


def test_duplicate_email_conflicts(client):
    client.post("/users", json={"name": "A", "email": "a@x.bt"}, headers=SYSTEM)
    assert client.post("/users", json={"name": "B", "email": "a@x.bt"}, headers=SYSTEM).status_code == 409


def test_citizens_cannot_create_list_or_read_others(client):
    client.post("/users", json={"id": "u-2", "name": "B", "email": "b@x.bt"}, headers=SYSTEM)
    citizen = {"X-User-Id": "u-3", "X-User-Role": "CITIZEN"}
    assert client.post("/users", json={"name": "C", "email": "c@x.bt"}, headers=citizen).status_code == 403
    assert client.get("/users", headers=citizen).status_code == 403
    assert client.get("/users/u-2", headers=citizen).status_code == 403
    assert client.get("/users/u-2", headers=ADMIN).status_code == 200
