from conftest import CITIZEN


def test_service_boots(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert "thimphu" in client.get("/weather", headers=CITIZEN).json()


# TODO(D2): test the Open-Meteo call with httpx.MockTransport (see services/auth/conftest.py)
#           and the cache hit / Redis-down paths.
