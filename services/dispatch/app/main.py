"""Dispatch service: the queue worker that assigns the nearest free team + vehicle to a verified incident.

For every message on ``dispatch.requests``:
  1. (optional) wait PROCESSING_DELAY_SECONDS  - "route calculation + confirming with the team"
  2. check the incident is still VERIFIED      - makes redelivered messages harmless
  3. GET available responders and vehicles     - Responder / Vehicle services
  4. POST both lists to Location /nearest      - sorted by Haversine distance
  5. claim the nearest responder, then vehicle - atomic claim; on 409 try the next one
  6. publish dispatch.assigned                 - Incident, Notification, Analytics, Audit react

The message is acked only after step 6, so if this pod dies mid-way another pod
redoes the work. This queue's depth is what the HPA scales on (2 -> 6 pods).

A second consumer frees units when an incident is RESOLVED or CANCELLED.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from prometheus_client import Counter, Histogram

from drukcommon import DISPATCH_QUEUE, Event, Principal, Role, create_app, create_event_bus, require_roles
from drukcommon.config import env_float, env_int
from drukcommon.http import service_client
from drukcommon.metrics import trace_exemplar
from drukcommon.timeutil import iso, parse_iso, utcnow

log = logging.getLogger("dispatch")
bus = create_event_bus("dispatch")

PROCESSING_DELAY_SECONDS = env_float("PROCESSING_DELAY_SECONDS", 0.0)
MAX_ATTEMPTS = env_int("DISPATCH_MAX_ATTEMPTS", 3)
RETRY_DELAY_SECONDS = env_float("DISPATCH_RETRY_DELAY_SECONDS", 5.0)
CLAIM_CANDIDATES = env_int("DISPATCH_CLAIM_CANDIDATES", 5)

# Which vehicle kinds suit which incident; anything else is a fallback.
VEHICLE_PREFERENCE: dict[str, list[str]] = {
    "FIRE": ["FIRE_TRUCK"],
    "MEDICAL": ["AMBULANCE"],
    "ACCIDENT": ["AMBULANCE", "POLICE"],
    "FLOOD": ["RESCUE", "AMBULANCE"],
    "GLOF": ["RESCUE", "AMBULANCE"],
    "LANDSLIDE": ["RESCUE", "AMBULANCE"],
    "EARTHQUAKE": ["RESCUE", "AMBULANCE"],
}

TIME_TO_DISPATCH = Histogram(
    "drukrescue_time_to_dispatch_seconds",
    "Seconds from an incident being reported to a team being assigned",
    buckets=(1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600),
)
OUTCOMES = Counter("drukrescue_dispatch_outcomes_total", "Dispatch attempts by outcome", ["outcome"])

_clients: dict[str, httpx.Client] = {}


def client(service: str) -> httpx.Client:
    if service not in _clients:
        _clients[service] = service_client(service)
    return _clients[service]


@dataclass
class Assignment:
    responder: dict
    vehicle: dict


# --- the dispatch algorithm ---------------------------------------------------------------
def rank(origin: dict, units: list[dict]) -> list[dict]:
    res = client("location").post("/location/nearest", json={"origin": origin, "units": units})
    res.raise_for_status()
    return res.json()["results"]


def prefer_vehicle_kinds(ranked: list[dict], incident_type: str) -> list[dict]:
    preferred = VEHICLE_PREFERENCE.get(incident_type, [])
    # sorted() is stable: within each group, nearest stays first.
    return sorted(ranked, key=lambda v: preferred.index(v["kind"]) if v.get("kind") in preferred else len(preferred))


def claim_first(service: str, collection: str, candidates: list[dict], incident_id: str) -> dict | None:
    for unit in candidates[:CLAIM_CANDIDATES]:
        res = client(service).post(f"/{collection}/{unit['id']}/claim", json={"incident_id": incident_id})
        if res.status_code == 409:
            continue  # another Dispatch pod got there first; try the next nearest
        res.raise_for_status()
        return {**unit, **res.json()}
    return None


def release(service: str, collection: str, unit_id: int, incident_id: str) -> None:
    try:
        client(service).post(f"/{collection}/{unit_id}/release", json={"incident_id": incident_id})
    except httpx.HTTPError:
        log.exception("could not release unit", extra={"service": service, "unit_id": unit_id})


def find_and_claim(req: dict) -> Assignment | None:
    incident_id = req["incident_id"]
    origin = {"lat": req["lat"], "lng": req["lng"]}

    res = client("responder").get("/responders", params={"status": "AVAILABLE"})
    res.raise_for_status()
    excluded = set(req.get("excluded_responder_ids") or [])
    responders = [r for r in res.json() if r["id"] not in excluded]
    res = client("vehicle").get("/vehicles", params={"status": "AVAILABLE"})
    res.raise_for_status()
    vehicles = res.json()
    if not responders or not vehicles:
        return None

    responder = claim_first("responder", "responders", rank(origin, responders), incident_id)
    if responder is None:
        return None
    vehicle = claim_first("vehicle", "vehicles", prefer_vehicle_kinds(rank(origin, vehicles), req.get("type", "")), incident_id)
    if vehicle is None:
        release("responder", "responders", responder["id"], incident_id)
        return None
    return Assignment(responder, vehicle)


def retry_later(req: dict, reason: str) -> None:
    attempt = int(req.get("attempt", 1))
    if attempt >= MAX_ATTEMPTS:
        OUTCOMES.labels("unassigned").inc()
        log.warning("giving up on incident", extra={"incident_id": req["incident_id"], "reason": reason})
        bus.publish("dispatch.unassigned", {"incident_id": req["incident_id"], "reason": reason, "attempts": attempt})
        return
    OUTCOMES.labels("retried").inc()
    log.info("will retry", extra={"incident_id": req["incident_id"], "reason": reason, "attempt": attempt})
    time.sleep(RETRY_DELAY_SECONDS)
    bus.enqueue(DISPATCH_QUEUE, "dispatch.requested", {**req, "attempt": attempt + 1})


@bus.consumer(DISPATCH_QUEUE)
def handle_dispatch_request(event: Event) -> None:
    req = event.data
    incident_id = req["incident_id"]
    if PROCESSING_DELAY_SECONDS:
        time.sleep(PROCESSING_DELAY_SECONDS)

    try:
        res = client("incident").get(f"/incidents/{incident_id}")
        if res.status_code == 404:
            OUTCOMES.labels("skipped").inc()
            return
        res.raise_for_status()
        incident = res.json()
        if incident["status"] != "VERIFIED":
            OUTCOMES.labels("skipped").inc()
            log.info("incident no longer needs dispatch", extra={"incident_id": incident_id, "status": incident["status"]})
            return
        assignment = find_and_claim(req)
    except httpx.HTTPError:
        log.exception("dependency failed during dispatch", extra={"incident_id": incident_id})
        retry_later(req, "A dependency was unavailable")
        return

    if assignment is None:
        retry_later(req, "No free responder and vehicle")
        return

    reported_at = parse_iso(req.get("reported_at")) or parse_iso(incident.get("created_at")) or utcnow()
    seconds = max((utcnow() - reported_at).total_seconds(), 0.0)
    r, v = assignment.responder, assignment.vehicle
    payload = {
        "incident_id": incident_id,
        "incident_type": req.get("type"),
        "severity": req.get("severity"),
        "district": req.get("district"),
        "location_name": req.get("location_name"),
        "reporter_id": req.get("reporter_id") or incident.get("reporter_id"),
        "responder_id": r["id"],
        "responder_user_id": r.get("user_id"),
        "responder_name": r.get("name"),
        "team": r.get("team"),
        "vehicle_id": v["id"],
        "vehicle_name": v.get("registration"),
        "vehicle_kind": v.get("kind"),
        "distance_km": r.get("distance_km"),
        "eta_minutes": max(r.get("eta_minutes") or 0, v.get("eta_minutes") or 0) or None,
        "time_to_dispatch_seconds": round(seconds, 2),
        "assigned_at": iso(utcnow()),
    }
    try:
        bus.publish("dispatch.assigned", payload)
    except Exception:
        # Don't leave units stuck BUSY; the message will be redelivered and retried.
        release("responder", "responders", r["id"], incident_id)
        release("vehicle", "vehicles", v["id"], incident_id)
        raise
    TIME_TO_DISPATCH.observe(seconds, exemplar=trace_exemplar())
    OUTCOMES.labels("assigned").inc()
    log.info("dispatched", extra={"incident_id": incident_id, "responder_id": r["id"], "vehicle_id": v["id"],
                                  "time_to_dispatch_seconds": payload["time_to_dispatch_seconds"]})


@bus.consumer("dispatch.releases", ["incident.status_changed", "dispatch.release_requested"])
def handle_release(event: Event) -> None:
    data = event.data
    if event.type == "incident.status_changed" and data.get("status") not in ("RESOLVED", "CANCELLED"):
        return
    incident_id = data.get("incident_id") or data.get("id")
    for service, collection, key in (("responder", "responders", "assigned_responder_id"),
                                     ("vehicle", "vehicles", "assigned_vehicle_id")):
        unit_id = data.get(key)
        if unit_id is None:
            continue
        res = client(service).post(f"/{collection}/{unit_id}/release", json={"incident_id": incident_id})
        if res.status_code != 404:
            res.raise_for_status()  # let the bus retry once, then dead-letter
    log.info("units released", extra={"incident_id": incident_id})


# --- HTTP ---------------------------------------------------------------------------------
router = APIRouter(prefix="/dispatch", tags=["dispatch"])
admin = require_roles(Role.ADMIN)


@router.get("/config")
def config(_: Principal = Depends(admin)):
    return {
        "processing_delay_seconds": PROCESSING_DELAY_SECONDS,
        "max_attempts": MAX_ATTEMPTS,
        "retry_delay_seconds": RETRY_DELAY_SECONDS,
        "vehicle_preference": VEHICLE_PREFERENCE,
    }


@router.post("/manual")
def manual_dispatch(_: Principal = Depends(admin)):
    # TODO(C3): admin picks the responder + vehicle for a VERIFIED incident. See TASKS.md.
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Manual dispatch is not implemented yet (TASKS.md C3)")


def _close_clients() -> None:
    for c in _clients.values():
        c.close()


app = create_app(service="dispatch", title="DrukRescue Dispatch", bus=bus, on_shutdown=[_close_clients])
app.include_router(router)
