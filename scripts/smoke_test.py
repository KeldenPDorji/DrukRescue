#!/usr/bin/env python3
"""End-to-end smoke test of the demo flow, through the gateway, against a running stack.

    python3 scripts/smoke_test.py                              # docker-compose
    python3 scripts/smoke_test.py --base http://drukrescue.local

report -> verify -> dispatched to the nearest team -> notifications -> en route -> on scene -> resolved -> units freed.
Creates its own uniquely-named responder, vehicle and citizen in Gasa so the result is deterministic.
Admin credentials: ADMIN_EMAIL / ADMIN_PASSWORD, falling back to .env. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import secrets
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
GASA = (27.9050, 89.7270)


class Api:
    def __init__(self, base: str, token: str | None = None):
        self.base, self.token = base.rstrip("/") + "/api", token

    def call(self, method: str, path: str, body: dict | None = None, expect: int | None = None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                status, data = res.status, json.loads(res.read() or b"null")
        except urllib.error.HTTPError as err:
            status, data = err.code, err.read().decode()[:300]
        except urllib.error.URLError as err:
            fail(f"cannot reach {self.base} ({err.reason}). Is the stack running? (make up)")
        if expect is not None and status != expect:
            fail(f"{method} {path}: expected {expect}, got {status}: {data}")
        return data


def fail(msg: str) -> None:
    print(f"FAIL  {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"ok    {msg}")


def wait_for(fn, what: str, timeout: float = 30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if result := fn():
            return result
        time.sleep(1)
    fail(f"timed out waiting for {what}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default=os.getenv("DRUKRESCUE_URL", "http://localhost:8000"))
    base = p.parse_args().base

    dotenv = {}
    if (ROOT / ".env").exists():
        lines = (ROOT / ".env").read_text().splitlines()
        dotenv = dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
    email = os.getenv("ADMIN_EMAIL") or dotenv.get("BOOTSTRAP_ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD") or dotenv.get("BOOTSTRAP_ADMIN_PASSWORD")
    if not email or not password:
        fail("set ADMIN_EMAIL / ADMIN_PASSWORD or create .env")

    anon = Api(base)
    anon.call("GET", "/incidents", expect=401)
    ok("gateway rejects requests without a token")

    admin = Api(base, anon.call("POST", "/auth/login", {"email": email, "password": password}, expect=200)["access_token"])
    ok("admin login")

    run = secrets.token_hex(3)
    pw = secrets.token_urlsafe(12)
    resp_email, citizen_email = f"smoke-r-{run}@drukrescue.bt", f"smoke-c-{run}@drukrescue.bt"
    resp_account = admin.call("POST", "/auth/accounts", {"name": f"Smoke Responder {run}", "email": resp_email,
                                                         "password": pw, "role": "RESPONDER"}, expect=201)
    responder = admin.call("POST", "/responders", {"name": f"Smoke {run}", "team": f"Smoke Team {run}", "district": "Gasa",
                                                   "lat": GASA[0], "lng": GASA[1], "user_id": resp_account["id"]}, expect=201)
    vehicle = admin.call("POST", "/vehicles", {"registration": f"SMK-{run}", "kind": "RESCUE", "district": "Gasa",
                                               "lat": GASA[0], "lng": GASA[1]}, expect=201)
    ok(f"created responder {responder['id']} and vehicle {vehicle['id']} in Gasa")

    citizen = Api(base, anon.call("POST", "/auth/register", {"name": "Smoke Citizen", "email": citizen_email,
                                                             "password": pw}, expect=201)["access_token"])
    rsp = Api(base, anon.call("POST", "/auth/login", {"email": resp_email, "password": pw}, expect=200)["access_token"])

    citizen.call("POST", "/incidents/INC-x/verify", expect=403)
    ok("citizen cannot verify (RBAC)")

    inc = citizen.call("POST", "/incidents", {"type": "FLOOD", "severity": "HIGH", "description": f"Smoke test {run}",
                                              "lat": GASA[0] + 0.001, "lng": GASA[1], "district": "Gasa",
                                              "location_name": "Gasa"}, expect=201)
    code = inc["id"]
    ok(f"citizen reported {code} ({inc['status']})")

    admin.call("POST", f"/incidents/{code}/verify", expect=200)
    ok("admin verified")

    dispatched = wait_for(lambda: (i := citizen.call("GET", f"/incidents/{code}")) and i["status"] == "DISPATCHED" and i,
                          "dispatch (is the dispatch service consuming dispatch.requests?)")
    if dispatched["assigned_responder_id"] != responder["id"] or dispatched["assigned_vehicle_id"] != vehicle["id"]:
        got = f"{dispatched['assigned_responder_id']}/{dispatched['assigned_vehicle_id']}"
        fail(f"expected nearest units {responder['id']}/{vehicle['id']}, got {got}")
    ok(f"dispatched nearest team: {dispatched['assigned_team']} with {dispatched['assigned_vehicle_name']}")

    wait_for(lambda: any(n["title"] == "Rescue team dispatched" for n in citizen.call("GET", "/notifications/me")),
             "citizen notification")
    wait_for(lambda: any(n["title"] == "New assignment" for n in rsp.call("GET", "/notifications/me")), "responder notification")
    ok("citizen and responder notified")

    for stage, status in [("EN_ROUTE", "DISPATCHED"), ("ON_SCENE", "IN_PROGRESS"), ("RESOLVED", "RESOLVED")]:
        got = rsp.call("POST", f"/incidents/{code}/progress", {"stage": stage}, expect=200)["status"]
        if got != status:
            fail(f"{stage}: expected {status}, got {got}")
    ok("responder: en route -> on scene -> resolved")

    wait_for(lambda: admin.call("GET", f"/responders/{responder['id']}")["status"] == "AVAILABLE", "responder release")
    wait_for(lambda: admin.call("GET", f"/vehicles/{vehicle['id']}")["status"] == "AVAILABLE", "vehicle release")
    ok("units released after resolution")

    timeline = [t["stage"] or t["status"] for t in citizen.call("GET", f"/incidents/{code}/timeline")]
    ok(f"timeline: {' -> '.join(timeline)}")

    # Tidy up so the smoke units don't get picked for real incidents.
    admin.call("PATCH", f"/responders/{responder['id']}", {"status": "OFFLINE"})
    admin.call("PATCH", f"/vehicles/{vehicle['id']}", {"status": "OUT_OF_SERVICE"})
    print("\nPASS  end-to-end flow works")


if __name__ == "__main__":
    main()
