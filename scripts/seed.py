#!/usr/bin/env python3
"""Seed demo data through the public API (so it exercises the gateway, auth and RBAC).

    python3 scripts/seed.py                              # docker-compose: http://localhost:8000
    python3 scripts/seed.py --base http://drukrescue.local

Creates: responder teams + vehicles around Thimphu/Paro/Punakha, two responder logins and one citizen login.
Admin credentials are read from ADMIN_EMAIL / ADMIN_PASSWORD, falling back to .env (BOOTSTRAP_ADMIN_*).
Safe to re-run: existing items (409) are skipped. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import secrets
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent

# (team, district, lat, lng)
TEAMS = [
    ("Rescue Team 01", "Thimphu", 27.4728, 89.6390),
    ("Rescue Team 02", "Thimphu", 27.4980, 89.6300),
    ("Rescue Team 03", "Thimphu", 27.4300, 89.6500),
    ("Rescue Team 04", "Thimphu", 27.4450, 89.6480),  # Babesa
    ("Rescue Team 05", "Paro", 27.4305, 89.4133),
    ("Rescue Team 06", "Paro", 27.4000, 89.4300),
    ("Rescue Team 07", "Punakha", 27.5916, 89.8774),
    ("Rescue Team 08", "Wangdue Phodrang", 27.4860, 89.8990),
]
# (registration, kind, district, lat, lng)
VEHICLES = [
    ("BP-1-A0001", "AMBULANCE", "Thimphu", 27.4700, 89.6400),
    ("BP-1-A0002", "AMBULANCE", "Thimphu", 27.4400, 89.6470),
    ("BP-1-F0001", "FIRE_TRUCK", "Thimphu", 27.4750, 89.6350),
    ("BP-1-R0001", "RESCUE", "Thimphu", 27.4460, 89.6490),
    ("BP-1-R0002", "RESCUE", "Thimphu", 27.4900, 89.6320),
    ("BP-1-P0001", "POLICE", "Thimphu", 27.4720, 89.6380),
    ("BP-2-A0001", "AMBULANCE", "Paro", 27.4300, 89.4150),
    ("BP-2-R0001", "RESCUE", "Paro", 27.4050, 89.4280),
    ("BP-3-A0001", "AMBULANCE", "Punakha", 27.5900, 89.8780),
    ("BP-3-R0001", "RESCUE", "Wangdue Phodrang", 27.4850, 89.9000),
]


def read_dotenv() -> dict[str, str]:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return {}
    pairs = (line.split("=", 1) for line in env_file.read_text().splitlines() if "=" in line and not line.startswith("#"))
    return {k.strip(): v.strip() for k, v in pairs}


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/") + "/api"
        self.token: str | None = None

    def call(self, method: str, path: str, body: dict | None = None, ok_conflict: bool = True):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return json.loads(res.read() or b"null")
        except urllib.error.HTTPError as err:
            if err.code == 409 and ok_conflict:
                return None
            sys.exit(f"{method} {path} -> {err.code}: {err.read().decode()[:300]}")
        except urllib.error.URLError as err:
            sys.exit(f"Cannot reach {self.base} ({err.reason}). Is the stack running? (make up)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default=os.getenv("DRUKRESCUE_URL", "http://localhost:8000"))
    args = parser.parse_args()

    dotenv = read_dotenv()
    email = os.getenv("ADMIN_EMAIL") or dotenv.get("BOOTSTRAP_ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD") or dotenv.get("BOOTSTRAP_ADMIN_PASSWORD")
    if not email or not password:
        sys.exit("Set ADMIN_EMAIL and ADMIN_PASSWORD (or create .env with `make env`).")

    api = Api(args.base)
    api.token = api.call("POST", "/auth/login", {"email": email, "password": password}, ok_conflict=False)["access_token"]
    print(f"Logged in as {email}")

    existing = {r["team"] for r in api.call("GET", "/responders")}
    demo_password = secrets.token_urlsafe(9)
    created_logins = []
    for i, (team, district, lat, lng) in enumerate(TEAMS):
        if team in existing:
            continue
        user_id = None
        if i < 2:  # two teams get a login so you can demo the responder view
            login_email = f"responder{i + 1}@drukrescue.bt"
            account = api.call("POST", "/auth/accounts", {"name": f"Responder {i + 1}", "email": login_email,
                                                          "password": demo_password, "role": "RESPONDER"})
            if account:
                user_id = account["id"]
                created_logins.append(login_email)
        api.call("POST", "/responders", {"name": f"{team} lead", "team": team, "district": district,
                                         "lat": lat, "lng": lng, "user_id": user_id})
    print(f"Responders: {len(TEAMS)} teams")

    for registration, kind, district, lat, lng in VEHICLES:
        api.call("POST", "/vehicles", {"registration": registration, "kind": kind, "district": district, "lat": lat, "lng": lng})
    print(f"Vehicles: {len(VEHICLES)}")

    # TODO(B2): seed shelters once the Shelter service is implemented.
    # TODO(D1): seed resource stock once the Resource service is implemented.

    citizen = api.call("POST", "/auth/register", {"name": "Demo Citizen", "email": "citizen@drukrescue.bt",
                                                  "password": demo_password})
    if citizen:
        created_logins.append("citizen@drukrescue.bt")

    if created_logins:
        print("\nDemo logins created (password shown once):")
        for login in created_logins:
            print(f"  {login} / {demo_password}")


if __name__ == "__main__":
    main()
