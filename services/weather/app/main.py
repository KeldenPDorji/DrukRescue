"""Weather service (SCAFFOLD, see TASKS.md D2).

Fetches current weather for a district from Open-Meteo (free, no API key) and caches it in Redis.
The spec and acceptance criteria are in services/weather/README.md.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.districts import DISTRICTS
from drukcommon import Principal, create_app, get_principal

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("")
def list_districts(principal: Principal = Depends(get_principal)):
    return sorted(DISTRICTS)


@router.get("/{district}")
def weather_for(district: str, principal: Principal = Depends(get_principal)):
    # TODO(D2): look up coordinates, check Redis (key weather:<district>), else call Open-Meteo,
    #           cache for WEATHER_CACHE_SECONDS, return {district, current: {...}, cached, fetched_at}.
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet (TASKS.md D2)")


app = create_app(service="weather", title="DrukRescue Weather")
app.include_router(router)
