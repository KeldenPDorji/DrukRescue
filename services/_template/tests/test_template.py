from fastapi.testclient import TestClient

from app.main import app


def test_hello():
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        res = client.get("/template/hello", headers={"X-User-Id": "u1", "X-User-Role": "CITIZEN"})
        assert res.json() == {"hello": "u1", "role": "CITIZEN"}
        assert client.get("/template/hello").status_code == 401
