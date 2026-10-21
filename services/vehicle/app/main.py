"""Vehicle service: ambulances, fire trucks, rescue and police vehicles, their status and position."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, Vehicle, VehicleKind, VehicleStatus
from drukcommon import Database, Principal, Role, create_app, require_roles
from drukcommon.metrics import register_scrape_time_gauge
from drukcommon.timeutil import iso, utcnow

database = Database.from_settings()
get_db = database.get_db

admin = require_roles(Role.ADMIN)
admin_or_system = require_roles(Role.ADMIN, Role.SYSTEM)


class VehicleCreate(BaseModel):
    registration: str = Field(min_length=2, max_length=32)
    kind: VehicleKind
    district: str | None = Field(default=None, max_length=64)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class VehicleUpdate(BaseModel):
    kind: VehicleKind | None = None
    district: str | None = Field(default=None, max_length=64)
    status: VehicleStatus | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class Claim(BaseModel):
    incident_id: str = Field(max_length=32)


class Release(BaseModel):
    incident_id: str | None = Field(default=None, max_length=32)


def to_out(v: Vehicle) -> dict:
    return {
        "id": v.id, "registration": v.registration, "kind": v.kind, "district": v.district,
        "status": v.status, "lat": v.lat, "lng": v.lng,
        "current_incident_id": v.current_incident_id, "updated_at": iso(v.updated_at),
    }


def get_or_404(db: Session, vehicle_id: int) -> Vehicle:
    v = db.get(Vehicle, vehicle_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vehicle not found")
    return v


router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create(body: VehicleCreate, _: Principal = Depends(admin), db: Session = Depends(get_db)):
    v = Vehicle(**body.model_dump(), status=VehicleStatus.AVAILABLE)
    db.add(v)
    try:
        db.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Registration already exists") from None
    return to_out(v)


@router.get("")
def list_vehicles(
    status_: VehicleStatus | None = Query(default=None, alias="status"),
    kind: VehicleKind | None = None,
    district: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    _: Principal = Depends(admin_or_system),
    db: Session = Depends(get_db),
):
    q = select(Vehicle).order_by(Vehicle.id).limit(limit)
    if status_:
        q = q.where(Vehicle.status == status_)
    if kind:
        q = q.where(Vehicle.kind == kind)
    if district:
        q = q.where(Vehicle.district == district)
    return [to_out(v) for v in db.scalars(q)]


@router.get("/{vehicle_id}")
def get_one(vehicle_id: int, _: Principal = Depends(admin_or_system), db: Session = Depends(get_db)):
    return to_out(get_or_404(db, vehicle_id))


@router.patch("/{vehicle_id}")
def patch(vehicle_id: int, body: VehicleUpdate, _: Principal = Depends(admin), db: Session = Depends(get_db)):
    v = get_or_404(db, vehicle_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(v, key, value)
    db.commit()
    return to_out(v)


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(vehicle_id: int, _: Principal = Depends(admin), db: Session = Depends(get_db)):
    db.delete(get_or_404(db, vehicle_id))
    db.commit()


@router.post("/{vehicle_id}/claim")
def claim(vehicle_id: int, body: Claim, _: Principal = Depends(admin_or_system), db: Session = Depends(get_db)):
    """Atomic AVAILABLE -> BUSY; see the responder service for why this is a conditional UPDATE."""
    result = db.execute(
        update(Vehicle)
        .where(Vehicle.id == vehicle_id, Vehicle.status == VehicleStatus.AVAILABLE)
        .values(status=VehicleStatus.BUSY, current_incident_id=body.incident_id, updated_at=utcnow())
    )
    db.commit()
    if result.rowcount == 0:
        get_or_404(db, vehicle_id)
        raise HTTPException(status.HTTP_409_CONFLICT, "Vehicle is not available")
    return to_out(get_or_404(db, vehicle_id))


@router.post("/{vehicle_id}/release")
def release(vehicle_id: int, body: Release, _: Principal = Depends(admin_or_system), db: Session = Depends(get_db)):
    v = get_or_404(db, vehicle_id)
    if body.incident_id and v.current_incident_id != body.incident_id:
        return to_out(v)
    v.current_incident_id = None
    if v.status == VehicleStatus.BUSY:
        v.status = VehicleStatus.AVAILABLE
    db.commit()
    return to_out(v)


def _available_count():
    with database.session() as db:
        n = db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.status == VehicleStatus.AVAILABLE))
    return [(("vehicle",), n or 0)]


register_scrape_time_gauge(
    "drukrescue_units_available", "Units currently available for dispatch", ["kind"], _available_count
)

app = create_app(service="vehicle", title="DrukRescue Vehicle", database=database, models_base=Base)
app.include_router(router)
