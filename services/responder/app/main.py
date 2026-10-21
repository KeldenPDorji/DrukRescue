"""Responder service: rescue teams, their status (AVAILABLE/BUSY/OFFLINE) and last known position."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Base, Responder, ResponderStatus
from drukcommon import Database, Principal, Role, create_app, require_roles
from drukcommon.metrics import register_scrape_time_gauge
from drukcommon.timeutil import iso, utcnow

database = Database.from_settings()
get_db = database.get_db

admin = require_roles(Role.ADMIN)
admin_or_system = require_roles(Role.ADMIN, Role.SYSTEM)
responder_only = require_roles(Role.RESPONDER)


class ResponderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    team: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    district: str | None = Field(default=None, max_length=64)
    user_id: str | None = Field(default=None, max_length=64)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class ResponderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    team: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    district: str | None = Field(default=None, max_length=64)
    user_id: str | None = Field(default=None, max_length=64)
    status: ResponderStatus | None = None


class StatusUpdate(BaseModel):
    status: ResponderStatus


class LocationUpdate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class Claim(BaseModel):
    incident_id: str = Field(max_length=32)


class Release(BaseModel):
    incident_id: str | None = Field(default=None, max_length=32)


def to_out(r: Responder) -> dict:
    return {
        "id": r.id, "user_id": r.user_id, "name": r.name, "team": r.team, "phone": r.phone,
        "district": r.district, "status": r.status, "lat": r.lat, "lng": r.lng,
        "current_incident_id": r.current_incident_id, "updated_at": iso(r.updated_at),
    }


def get_or_404(db: Session, responder_id: int) -> Responder:
    r = db.get(Responder, responder_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Responder not found")
    return r


def get_mine(db: Session, principal: Principal) -> Responder:
    r = db.scalar(select(Responder).where(Responder.user_id == principal.user_id))
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No responder profile is linked to this account")
    return r


router = APIRouter(prefix="/responders", tags=["responders"])


# --- the responder's own profile (declared before /{responder_id} so "me" isn't parsed as an id) ---
@router.get("/me")
def get_me(principal: Principal = Depends(responder_only), db: Session = Depends(get_db)):
    return to_out(get_mine(db, principal))


@router.patch("/me/status")
def set_my_status(body: StatusUpdate, principal: Principal = Depends(responder_only), db: Session = Depends(get_db)):
    r = get_mine(db, principal)
    if body.status == ResponderStatus.BUSY:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "BUSY is set by Dispatch, not manually")
    if r.current_incident_id and body.status == ResponderStatus.AVAILABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Still assigned to {r.current_incident_id}")
    r.status = body.status
    db.commit()
    return to_out(r)


@router.patch("/me/location")
def set_my_location(body: LocationUpdate, principal: Principal = Depends(responder_only), db: Session = Depends(get_db)):
    r = get_mine(db, principal)
    r.lat, r.lng = body.lat, body.lng
    db.commit()
    return to_out(r)


# --- admin / internal ----------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED)
def create(body: ResponderCreate, _: Principal = Depends(admin), db: Session = Depends(get_db)):
    r = Responder(**body.model_dump(), status=ResponderStatus.AVAILABLE)
    db.add(r)
    db.commit()
    return to_out(r)


@router.get("")
def list_responders(
    status_: ResponderStatus | None = Query(default=None, alias="status"),
    district: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    _: Principal = Depends(admin_or_system),
    db: Session = Depends(get_db),
):
    q = select(Responder).order_by(Responder.id).limit(limit)
    if status_:
        q = q.where(Responder.status == status_)
    if district:
        q = q.where(Responder.district == district)
    return [to_out(r) for r in db.scalars(q)]


@router.get("/{responder_id}")
def get_one(responder_id: int, _: Principal = Depends(admin_or_system), db: Session = Depends(get_db)):
    return to_out(get_or_404(db, responder_id))


@router.patch("/{responder_id}")
def patch(responder_id: int, body: ResponderUpdate, _: Principal = Depends(admin), db: Session = Depends(get_db)):
    r = get_or_404(db, responder_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(r, key, value)
    db.commit()
    return to_out(r)


@router.delete("/{responder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(responder_id: int, _: Principal = Depends(admin), db: Session = Depends(get_db)):
    db.delete(get_or_404(db, responder_id))
    db.commit()


@router.post("/{responder_id}/claim")
def claim(responder_id: int, body: Claim, _: Principal = Depends(admin_or_system), db: Session = Depends(get_db)):
    """Atomically mark a responder BUSY. Two Dispatch pods can race for the same responder;
    the conditional UPDATE guarantees only one of them wins (the other gets 409 and tries the next)."""
    result = db.execute(
        update(Responder)
        .where(Responder.id == responder_id, Responder.status == ResponderStatus.AVAILABLE)
        .values(status=ResponderStatus.BUSY, current_incident_id=body.incident_id, updated_at=utcnow())
    )
    db.commit()
    if result.rowcount == 0:
        get_or_404(db, responder_id)
        raise HTTPException(status.HTTP_409_CONFLICT, "Responder is not available")
    return to_out(get_or_404(db, responder_id))


@router.post("/{responder_id}/release")
def release(responder_id: int, body: Release, _: Principal = Depends(admin_or_system), db: Session = Depends(get_db)):
    """Free a responder after an incident is resolved/cancelled. Only releases the given incident's claim."""
    r = get_or_404(db, responder_id)
    if body.incident_id and r.current_incident_id != body.incident_id:
        return to_out(r)  # already released or re-assigned: nothing to do (idempotent)
    r.current_incident_id = None
    if r.status == ResponderStatus.BUSY:
        r.status = ResponderStatus.AVAILABLE
    db.commit()
    return to_out(r)


def _available_count():
    with database.session() as db:
        n = db.scalar(select(func.count()).select_from(Responder).where(Responder.status == ResponderStatus.AVAILABLE))
    return [(("responder",), n or 0)]


register_scrape_time_gauge(
    "drukrescue_units_available", "Units currently available for dispatch", ["kind"], _available_count
)

app = create_app(service="responder", title="DrukRescue Responder", database=database, models_base=Base)
app.include_router(router)
