"""Location service: a stateless geo helper. Given a point and a list of units, sort them by distance."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.geo import estimate_minutes, haversine_km, rank_by_distance
from drukcommon import create_app
from drukcommon.config import env_float

AVG_SPEED_KMH = env_float("AVG_SPEED_KMH", 30.0)
ROAD_FACTOR = env_float("ROAD_FACTOR", 1.4)


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class Unit(BaseModel):
    # Callers may send any extra fields (name, kind, ...); they are echoed back.
    model_config = ConfigDict(extra="allow")
    id: int | str
    lat: float | None = None
    lng: float | None = None


class NearestRequest(BaseModel):
    origin: Point
    units: list[Unit] = Field(max_length=5000)
    limit: int | None = Field(default=None, ge=1, le=500)


router = APIRouter(prefix="/location", tags=["location"])


@router.post("/nearest")
def nearest(body: NearestRequest):
    ranked = rank_by_distance(body.origin.lat, body.origin.lng, [u.model_dump() for u in body.units])
    if body.limit:
        ranked = ranked[: body.limit]
    for unit in ranked:
        unit["eta_minutes"] = estimate_minutes(unit["distance_km"], AVG_SPEED_KMH, ROAD_FACTOR)
    return {"origin": body.origin, "results": ranked}


@router.get("/distance")
def distance(lat1: float, lng1: float, lat2: float, lng2: float):
    km = haversine_km(lat1, lng1, lat2, lng2)
    return {"distance_km": round(km, 3), "eta_minutes": estimate_minutes(km, AVG_SPEED_KMH, ROAD_FACTOR)}


app = create_app(service="location", title="DrukRescue Location")
app.include_router(router)
