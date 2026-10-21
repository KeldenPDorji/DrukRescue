import httpx
import pytest
from conftest import token_for

from app.rules import allowed_roles, resolve_service


def test_routes_to_service_and_forwards_path_and_query(client):
    res = client.get("/api/incidents/INC-2026-001", params={"x": "1"}, headers=token_for("ADMIN"))
    body = res.json()
    assert body["host"] == "incident"
    assert body["path"] == "/incidents/INC-2026-001"
    assert body["query"] == "x=1"


def test_public_routes_need_no_token(client):
    res = client.post("/api/auth/login", json={"email": "a@b.bt", "password": "x"})
    assert res.status_code == 200
    assert "x-user-id" not in res.json()["headers"]


def test_missing_bad_or_expired_token(client):
    assert client.get("/api/incidents").status_code == 401
    assert client.get("/api/incidents", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    assert client.get("/api/incidents", headers=token_for("CITIZEN", ttl=-1)).json()["detail"] == "Token expired"


def test_identity_headers_are_replaced_not_trusted(client):
    forged = {**token_for("CITIZEN", user_id="real-user"), "X-User-Id": "admin-1", "X-User-Role": "ADMIN"}
    headers = client.get("/api/incidents", headers=forged).json()["headers"]
    assert headers["x-user-id"] == "real-user"
    assert headers["x-user-role"] == "CITIZEN"
    assert "authorization" not in headers  # the JWT stays at the edge
    assert headers["x-request-id"]


@pytest.mark.parametrize(
    ("role", "method", "path", "status"),
    [
        ("CITIZEN", "post", "/api/incidents/INC-1/verify", 403),
        ("ADMIN", "post", "/api/incidents/INC-1/verify", 200),
        ("CITIZEN", "post", "/api/incidents/INC-1/progress", 403),
        ("RESPONDER", "post", "/api/incidents/INC-1/progress", 200),
        ("ADMIN", "post", "/api/responders/1/claim", 403),  # internal only
        ("ADMIN", "post", "/api/users", 403),  # internal only
        ("RESPONDER", "get", "/api/responders/me", 200),
        ("RESPONDER", "get", "/api/responders", 403),
        ("CITIZEN", "get", "/api/shelters", 200),
        ("CITIZEN", "post", "/api/alerts", 403),
        ("CITIZEN", "get", "/api/audit", 403),
        ("CITIZEN", "post", "/api/incidents", 200),
    ],
)
def test_role_rules(client, role, method, path, status):
    assert getattr(client, method)(path, headers=token_for(role)).status_code == status


def test_unknown_route_and_traversal(client):
    assert client.get("/api/nope", headers=token_for("ADMIN")).status_code == 404
    assert resolve_service("/incidents/../users") == "incident"
    assert client.get("/api/incidents/%2E%2E/users", headers=token_for("ADMIN")).status_code == 400


def test_upstream_down_is_502(client, monkeypatch):
    import app.main as main

    def down(request):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(main, "upstream", httpx.AsyncClient(transport=httpx.MockTransport(down)))
    assert client.get("/api/incidents", headers=token_for("ADMIN")).status_code == 502


def test_rate_limit(client, monkeypatch):
    import app.main as main

    class Limiter:
        def __init__(self):
            self.counts = {}

        async def hit(self, key, limit, window_seconds=60):
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key] <= limit, 30

        async def close(self):
            pass

    monkeypatch.setattr(main, "limiter", Limiter())
    monkeypatch.setattr(main, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    login = lambda: client.post("/api/auth/login", json={})  # noqa: E731
    assert [login().status_code for _ in range(3)] == [200, 200, 429]
    assert login().headers["retry-after"] == "30"


def test_rules_table_defaults_to_any_authenticated_user():
    assert allowed_roles("GET", "/incidents") is None
    assert allowed_roles("GET", "/weather/thimphu") is None
