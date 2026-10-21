"""Audit service (SCAFFOLD, see TASKS.md A1).

Consumes every event on the drukrescue.events exchange (binding "#") and stores it as an
append-only log: who did what, when. Admins can query it.
The spec and acceptance criteria are in services/audit/README.md.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.models import Base
from drukcommon import Database, Event, Principal, Role, create_app, create_event_bus, require_roles

database = Database.from_settings()
get_db = database.get_db
bus = create_event_bus("audit")

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def query_log(_: Principal = Depends(require_roles(Role.ADMIN))):
    # TODO(A1): filters ?event_type=&entity_id=&actor_id=&since=&limit=
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet (TASKS.md A1)")


@bus.consumer("audit.events", ["#"])
def on_event(event: Event) -> None:
    # TODO(A1): insert one AuditEntry per event; ignore duplicates (unique event id).
    pass


app = create_app(service="audit", title="DrukRescue Audit", database=database, models_base=Base, bus=bus)
app.include_router(router)
