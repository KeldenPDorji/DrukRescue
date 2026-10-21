"""Resource service (SCAFFOLD, see TASKS.md D1).

Supply counts per warehouse/district: medical kits, blankets, water, food, tents.
The spec and acceptance criteria are in services/resource/README.md.
Patterns to copy: services/vehicle (CRUD) and the atomic UPDATE in services/responder (claim).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.models import Base
from drukcommon import Database, Principal, create_app, get_principal

database = Database.from_settings()
get_db = database.get_db

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("")
def list_resources(principal: Principal = Depends(get_principal)):
    # TODO(D1): list stock, optional ?district= and ?item= filters.
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet (TASKS.md D1)")


# TODO(D1): GET /resources/low-stock, POST /resources, PATCH /resources/{id},
#           POST /resources/{id}/adjust {delta, reason}  (never below zero; atomic UPDATE)

app = create_app(service="resource", title="DrukRescue Resource", database=database, models_base=Base)
app.include_router(router)
