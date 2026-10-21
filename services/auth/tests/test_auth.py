from app.passwords import hash_password, verify_password
from drukcommon.auth import decode_access_token

SECRET = "test-secret-that-is-at-least-32-characters"


def test_password_hashing():
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("x", "garbage")


def test_register_creates_citizen_profile_and_token(client, users):
    res = client.post("/auth/register", json={"name": "Pema", "email": "pema@x.bt", "password": "password123"})
    assert res.status_code == 201, res.text
    body = res.json()
    claims = decode_access_token(body["access_token"], SECRET)
    assert claims["role"] == "CITIZEN"
    assert claims["sub"] in users.profiles


def test_register_ignores_role_and_rejects_duplicates(client):
    body = {"name": "A", "email": "a@x.bt", "password": "password123", "role": "ADMIN"}
    assert client.post("/auth/register", json=body).json()["user"]["role"] == "CITIZEN"
    assert client.post("/auth/register", json=body).status_code == 409


def test_register_fails_cleanly_when_user_service_down(client, users):
    users.down = True
    res = client.post("/auth/register", json={"name": "A", "email": "b@x.bt", "password": "password123"})
    assert res.status_code == 503


def test_login(client):
    client.post("/auth/register", json={"name": "A", "email": "c@x.bt", "password": "password123"})
    assert client.post("/auth/login", json={"email": "C@x.bt", "password": "password123"}).status_code == 200
    assert client.post("/auth/login", json={"email": "c@x.bt", "password": "nope-nope"}).status_code == 401
    assert client.post("/auth/login", json={"email": "nobody@x.bt", "password": "password123"}).status_code == 401


def test_bootstrap_admin_can_create_responder_accounts(client, users):
    login = client.post("/auth/login", json={"email": "admin@drukrescue.bt", "password": "admin-password-123"})
    assert login.status_code == 200
    admin = login.json()["user"]
    assert admin["role"] == "ADMIN"
    assert admin["id"] in users.profiles  # profile synced on startup/first login

    headers = {"X-User-Id": admin["id"], "X-User-Role": "ADMIN"}
    res = client.post("/auth/accounts", headers=headers,
                      json={"name": "Karma", "email": "karma@x.bt", "password": "password123", "role": "RESPONDER"})
    assert res.status_code == 201 and res.json()["role"] == "RESPONDER"

    citizen = {"X-User-Id": "c1", "X-User-Role": "CITIZEN"}
    res = client.post("/auth/accounts", headers=citizen,
                      json={"name": "x", "email": "x@x.bt", "password": "password123", "role": "ADMIN"})
    assert res.status_code == 403
