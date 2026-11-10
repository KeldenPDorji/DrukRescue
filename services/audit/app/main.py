"""Audit service: append-only log of every event on the platform.

Consumes every event on the drukrescue.events exchange (binding "#") and stores it.
Admins can query the log and verify its integrity via a hash chain.
"""

from __future__ import annotations

import hashlib
import json
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditEntry, Base
from drukcommon import Database, Event, Principal, Role, create_app, create_event_bus, require_roles
from drukcommon.timeutil import iso

log = logging.getLogger("audit")

database = Database.from_settings()
get_db = database.get_db
bus = create_event_bus("audit")


def _compute_hash(prev_hash: str, event_id: str, payload: str) -> str:
    return hashlib.sha256(f"{prev_hash}{event_id}{payload}".encode()).hexdigest()


def _extract_actor(data: dict) -> str | None:
    return data.get("actor_id") or data.get("reporter_id") or data.get("issued_by")


def _extract_entity(data: dict) -> str | None:
    val = data.get("incident_id") or data.get("id") or data.get("alert_id")
    return str(val) if val is not None else None


def to_out(entry: AuditEntry) -> dict:
    return {
        "id": entry.id,
        "event_id": entry.event_id,
        "event_type": entry.event_type,
        "source": entry.source,
        "actor_id": entry.actor_id,
        "entity_id": entry.entity_id,
        "occurred_at": entry.occurred_at,
        "payload": json.loads(entry.payload),
        "hash": entry.hash,
        "created_at": iso(entry.created_at),
    }


router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def query_log(
    event_type: str | None = None,
    entity_id: str | None = None,
    actor_id: str | None = None,
    since: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    _: Principal = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    q = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit)
    if event_type:
        q = q.where(AuditEntry.event_type == event_type)
    if entity_id:
        q = q.where(AuditEntry.entity_id == entity_id)
    if actor_id:
        q = q.where(AuditEntry.actor_id == actor_id)
    if since:
        q = q.where(AuditEntry.occurred_at >= since)
    return [to_out(e) for e in db.scalars(q)]


@router.get("/verify")
def verify_chain(
    _: Principal = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    entries = db.scalars(select(AuditEntry).order_by(AuditEntry.id)).all()
    total = len(entries)
    if total == 0:
        return {"ok": True, "checked": 0}

    prev_hash = "0" * 64
    for entry in entries:
        expected = _compute_hash(prev_hash, entry.event_id, entry.payload)
        if entry.hash != expected:
            return {
                "ok": False,
                "checked": total,
                "broken_at": entry.id,
                "detail": f"Entry {entry.id} hash mismatch",
            }
        prev_hash = entry.hash

    return {"ok": True, "checked": total}


@bus.consumer("audit.events", ["#"])
def on_event(event: Event) -> None:
    payload_str = json.dumps(event.data, default=str)
    with database.session() as db:
        last = db.scalar(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(1))
        prev_hash = last.hash if last else "0" * 64
        entry = AuditEntry(
            event_id=event.id,
            event_type=event.type,
            source=event.source,
            actor_id=_extract_actor(event.data),
            entity_id=_extract_entity(event.data),
            occurred_at=event.occurred_at,
            payload=payload_str,
            hash=_compute_hash(prev_hash, event.id, payload_str),
        )
        db.add(entry)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            log.info("duplicate event ignored", extra={"event_id": event.id})
            return
    log.info("audit entry stored", extra={"event_type": event.type, "event_id": event.id})


app = create_app(service="audit", title="DrukRescue Audit", database=database, models_base=Base, bus=bus)
app.include_router(router)
