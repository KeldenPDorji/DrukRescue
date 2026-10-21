"""Shelter service (SCAFFOLD, see TASKS.md B2).

Shelters: name, lat/lng, capacity, occupied. Citizens look up the nearest open shelters.
The spec and acceptance criteria are in services/shelter/README.md.
Patterns to copy: services/vehicle (CRUD) and services/dispatch (calling the Location service).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.models import Base
from drukcommon import Database, Principal, create_app, get_principal

database = Database.from_settings()
get_db = database.get_db

router = APIRouter(prefix="/shelters", tags=["shelters"])


@router.get("")
def list_shelters(principal: Principal = Depends(get_principal)):
    # TODO(B2): list shelters, optional ?district= and ?open_only= filters.
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet (TASKS.md B2)")


# TODO(B2): GET /shelters/nearby?lat=&lng=&limit=5  (use the Location service, like Dispatch does)
# TODO(B2): GET /shelters/{id}, POST /shelters, PATCH /shelters/{id}, DELETE /shelters/{id}  (writes: ADMIN only)

app = create_app(service="shelter", title="DrukRescue Shelter", database=database, models_base=Base)
app.include_router(router)
