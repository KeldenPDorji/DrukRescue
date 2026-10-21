def test_service_boots(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").status_code == 200
    assert "http_requests_total" in client.get("/metrics").text


# TODO: add tests for your endpoints and event handlers (see services/incident/tests for examples).
