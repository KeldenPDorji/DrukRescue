"""Incident service: create/read/update incidents, own the status lifecycle, publish events.

Flow (see docs/architecture.md):
  citizen POST /incidents -> REPORTED -> publishes incident.created
  admin POST /incidents/{id}/verify -> VERIFIED -> message on queue dispatch.requests
  consumes dispatch.assigned -> DISPATCHED
  responder POST /incidents/{id}/progress (EN_ROUTE, ON_SCENE -> IN_PROGRESS, RESOLVED)

Data is always committed to PostgreSQL *before* events are published, so a
RabbitMQ outage never loses a report (an admin can re-dispatch later).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from prometheus_client import Counter
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.lifecycle import ACTIVE, STAGE_RULES, TERMINAL, IncidentType, Severity, Stage, Status, can_transition
from app.models import Base, Incident, TimelineEntry
from drukcommon import (
    DISPATCH_QUEUE,
    Database,
    Event,
    Principal,
    Role,
    create_app,
    create_event_bus,
    get_principal,
    require_roles,
)
from drukcommon.config import env_bool
from drukcommon.metrics import register_scrape_time_gauge
from drukcommon.timeutil import iso, utcnow

log = logging.getLogger("incident")

database = Database.from_settings()
get_db = database.get_db
bus = create_event_bus("incident")

# Demo/load-test switch: verify every report automatically so it goes straight to Dispatch.
AUTO_VERIFY = env_bool("AUTO_VERIFY", False)

INCIDENTS_CREATED = Counter("drukrescue_incidents_created_total", "Incidents reported", ["type", "severity"])


# --- request bodies -----------------------------------------------------------------------
class IncidentCreate(BaseModel):
    type: IncidentType
    severity: Severity = Severity.MEDIUM
    description: str = Field(min_length=3, max_length=2000)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    district: str | None = Field(default=None, max_length=64)
    location_name: str | None = Field(default=None, max_length=128)
    photo_url: str | None = Field(default=None, max_length=512, pattern=r"^https?://")


class CancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class ProgressRequest(BaseModel):
    stage: Stage
    note: str | None = Field(default=None, max_length=500)


# --- helpers ------------------------------------------------------------------------------
def to_out(inc: Incident) -> dict:
    return {
        "id": inc.code,
        "type": inc.type,
        "severity": inc.severity,
        "status": inc.status,
        "description": inc.description,
        "lat": inc.lat,
        "lng": inc.lng,
        "district": inc.district,
        "location_name": inc.location_name,
        "photo_url": inc.photo_url,
        "reporter_id": inc.reporter_id,
        "assigned_responder_id": inc.assigned_responder_id,
        "assigned_responder_user_id": inc.assigned_responder_user_id,
        "assigned_responder_name": inc.assigned_responder_name,
        "assigned_team": inc.assigned_team,
        "assigned_vehicle_id": inc.assigned_vehicle_id,
        "assigned_vehicle_name": inc.assigned_vehicle_name,
        "eta_minutes": inc.eta_minutes,
        "created_at": iso(inc.created_at),
        "updated_at": iso(inc.updated_at),
        "verified_at": iso(inc.verified_at),
        "dispatched_at": iso(inc.dispatched_at),
        "resolved_at": iso(inc.resolved_at),
    }


def load(db: Session, code: str) -> Incident:
    inc = db.scalar(select(Incident).where(Incident.code == code))
    if inc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    return inc


def can_view(principal: Principal, inc: Incident) -> bool:
    if principal.has(Role.ADMIN, Role.SYSTEM):
        return True
    if principal.role == Role.RESPONDER:
        return inc.assigned_responder_user_id == principal.user_id or inc.reporter_id == principal.user_id
    return inc.reporter_id == principal.user_id


def load_visible(db: Session, code: str, principal: Principal) -> Incident:
    inc = load(db, code)
    if not can_view(principal, inc):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")  # don't reveal it exists
    return inc


def change_status(inc: Incident, target: Status, *, actor: str, note: str | None = None, stage: Stage | None = None) -> str:
    """Apply a lifecycle transition (caller commits). Returns the previous status."""
    previous = inc.status
    if target != previous:
        if not can_transition(previous, target):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot move incident from {previous} to {target}")
        inc.status = target
        now = utcnow()
        if target == Status.VERIFIED:
            inc.verified_at = now
        elif target == Status.DISPATCHED:
            inc.dispatched_at = now
        elif target in TERMINAL:
            inc.resolved_at = now
    inc.timeline.append(TimelineEntry(status=inc.status, stage=stage, note=note, actor_id=actor))
    return previous


def publish(routing_key: str, data: dict) -> None:
    try:
        bus.publish(routing_key, data)
    except Exception:
        log.exception("could not publish event", extra={"event_type": routing_key, "incident_id": data.get("id")})


def announce_status(inc: Incident, previous: str, *, actor: str, note: str | None = None, stage: Stage | None = None) -> None:
    """Call after commit. Emits incident.status_changed and, on VERIFIED, queues a dispatch request."""
    publish("incident.status_changed", {**to_out(inc), "from_status": previous, "stage": stage, "note": note, "actor_id": actor})
    if inc.status == Status.VERIFIED and previous != Status.VERIFIED:
        request_dispatch(inc)


def request_dispatch(inc: Incident) -> bool:
    try:
        bus.enqueue(
            DISPATCH_QUEUE,
            "dispatch.requested",
            {
                "incident_id": inc.code,
                "type": inc.type,
                "severity": inc.severity,
                "lat": inc.lat,
                "lng": inc.lng,
                "district": inc.district,
                "location_name": inc.location_name,
                "reporter_id": inc.reporter_id,
                "reported_at": iso(inc.created_at),
                "attempt": 1,
            },
        )
        return True
    except Exception:
        log.exception("could not queue dispatch request", extra={"incident_id": inc.code})
        return False


# --- routes -------------------------------------------------------------------------------
router = APIRouter(prefix="/incidents", tags=["incidents"])
admin = require_roles(Role.ADMIN)


@router.post("", status_code=status.HTTP_201_CREATED)
def create(body: IncidentCreate, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    if principal.role == Role.SYSTEM:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Incidents are reported by people")
    inc = Incident(**body.model_dump(), status=Status.REPORTED, reporter_id=principal.user_id)
    inc.timeline.append(TimelineEntry(status=Status.REPORTED, note="Report received", actor_id=principal.user_id))
    db.add(inc)
    db.flush()  # assigns inc.id
    inc.code = f"INC-{utcnow().year}-{inc.id:03d}"
    db.commit()
    INCIDENTS_CREATED.labels(inc.type, inc.severity).inc()
    log.info("incident reported", extra={"incident_id": inc.code, "type": inc.type, "severity": inc.severity})
    publish("incident.created", to_out(inc))

    if AUTO_VERIFY:
        previous = change_status(inc, Status.VERIFIED, actor="system:auto-verify", note="Auto-verified (demo mode)")
        db.commit()
        announce_status(inc, previous, actor="system:auto-verify")
    return to_out(inc)


@router.get("")
def list_incidents(
    status_: Status | None = Query(default=None, alias="status"),
    type_: IncidentType | None = Query(default=None, alias="type"),
    district: str | None = None,
    active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    q = select(Incident).order_by(Incident.id.desc()).limit(limit).offset(offset)
    if principal.role == Role.RESPONDER:
        q = q.where(Incident.assigned_responder_user_id == principal.user_id)
    elif principal.role == Role.CITIZEN:
        q = q.where(Incident.reporter_id == principal.user_id)
    if status_:
        q = q.where(Incident.status == status_)
    if type_:
        q = q.where(Incident.type == type_)
    if district:
        q = q.where(Incident.district == district)
    if active is not None:
        q = q.where(Incident.status.in_(ACTIVE if active else TERMINAL))
    return [to_out(i) for i in db.scalars(q)]


@router.get("/{code}")
def get_one(code: str, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return to_out(load_visible(db, code, principal))


@router.get("/{code}/timeline")
def timeline(code: str, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    inc = load_visible(db, code, principal)
    return [
        {"status": t.status, "stage": t.stage, "note": t.note, "actor_id": t.actor_id, "at": iso(t.created_at)}
        for t in inc.timeline
    ]


@router.post("/{code}/verify")
def verify(code: str, principal: Principal = Depends(admin), db: Session = Depends(get_db)):
    inc = load(db, code)
    previous = change_status(inc, Status.VERIFIED, actor=principal.user_id, note="Verified by command centre")
    db.commit()
    announce_status(inc, previous, actor=principal.user_id)
    return to_out(inc)


@router.post("/{code}/redispatch")
def redispatch(code: str, principal: Principal = Depends(admin), db: Session = Depends(get_db)):
    """Re-queue a VERIFIED incident (e.g. no unit was free earlier, or RabbitMQ was down)."""
    inc = load(db, code)
    if inc.status != Status.VERIFIED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only VERIFIED incidents can be re-dispatched")
    if not request_dispatch(inc):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Message broker unavailable")
    inc.timeline.append(TimelineEntry(status=inc.status, note="Re-dispatch requested", actor_id=principal.user_id))
    db.commit()
    return to_out(inc)


@router.post("/{code}/cancel")
def cancel(code: str, body: CancelRequest, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    inc = load_visible(db, code, principal)
    is_reporter = inc.reporter_id == principal.user_id
    if not (principal.role == Role.ADMIN or (is_reporter and inc.status == Status.REPORTED)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin, or the reporter before verification, can cancel")
    note = f"Cancelled: {body.reason}" if body.reason else "Cancelled"
    previous = change_status(inc, Status.CANCELLED, actor=principal.user_id, note=note)
    db.commit()
    announce_status(inc, previous, actor=principal.user_id, note=note)  # Dispatch frees the units
    return to_out(inc)


@router.post("/{code}/progress")
def progress(code: str, body: ProgressRequest, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    inc = load(db, code)
    is_assignee = principal.role == Role.RESPONDER and inc.assigned_responder_user_id == principal.user_id
    if not (is_assignee or principal.role == Role.ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the assigned responder (or an admin) can update progress")
    required, target = STAGE_RULES[body.stage]
    if inc.status != required:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.stage} needs status {required}, incident is {inc.status}")
    previous = change_status(inc, target, actor=principal.user_id, note=body.note, stage=body.stage)
    db.commit()
    announce_status(inc, previous, actor=principal.user_id, note=body.note, stage=body.stage)
    return to_out(inc)


# --- event consumers ----------------------------------------------------------------------
@bus.consumer("incident.dispatch-results", ["dispatch.assigned", "dispatch.unassigned"])
def on_dispatch_result(event: Event) -> None:
    data = event.data
    with database.session() as db:
        inc = db.scalar(select(Incident).where(Incident.code == data.get("incident_id")))
        if inc is None:
            log.warning("dispatch result for unknown incident", extra={"incident_id": data.get("incident_id")})
            return

        if event.type == "dispatch.unassigned":
            inc.timeline.append(TimelineEntry(status=inc.status, stage="AWAITING_UNITS",
                                              note=data.get("reason") or "No unit available", actor_id="system:dispatch"))
            db.commit()
            return

        if inc.status == Status.DISPATCHED and inc.assigned_responder_id == data.get("responder_id"):
            return  # duplicate delivery; already applied
        if inc.status != Status.VERIFIED:
            # Cancelled while Dispatch was working: give the units back.
            log.info("ignoring assignment", extra={"incident_id": inc.code, "status": inc.status})
            publish("dispatch.release_requested", {
                "incident_id": inc.code,
                "assigned_responder_id": data.get("responder_id"),
                "assigned_vehicle_id": data.get("vehicle_id"),
                "reason": f"incident is {inc.status}",
            })
            return

        inc.assigned_responder_id = data.get("responder_id")
        inc.assigned_responder_user_id = data.get("responder_user_id")
        inc.assigned_responder_name = data.get("responder_name")
        inc.assigned_team = data.get("team")
        inc.assigned_vehicle_id = data.get("vehicle_id")
        inc.assigned_vehicle_name = data.get("vehicle_name")
        inc.eta_minutes = data.get("eta_minutes")
        note = f"{data.get('team') or data.get('responder_name')} dispatched with {data.get('vehicle_name')}"
        previous = change_status(inc, Status.DISPATCHED, actor="system:dispatch", note=note)
        db.commit()
        announce_status(inc, previous, actor="system:dispatch", note=note)


# --- metrics ------------------------------------------------------------------------------
def _active_by_severity():
    with database.session() as db:
        rows = dict(db.execute(
            select(Incident.severity, func.count()).where(Incident.status.in_(ACTIVE)).group_by(Incident.severity)
        ).all())
    return [((s.value,), rows.get(s.value, 0)) for s in Severity]


register_scrape_time_gauge("drukrescue_incidents_active", "Incidents not yet resolved or cancelled", ["severity"],
                           _active_by_severity)

app = create_app(service="incident", title="DrukRescue Incident", database=database, models_base=Base, bus=bus)
app.include_router(router)
