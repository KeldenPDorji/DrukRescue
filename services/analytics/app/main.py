"""Analytics service (SCAFFOLD, see TASKS.md D3).

Consumes incident/dispatch events, keeps its own copy of the facts it needs,
and serves GET /analytics/stats (incidents by type, average time to dispatch, ...).
The spec and acceptance criteria are in services/analytics/README.md; event payloads are in docs/events.md.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.models import Base
from drukcommon import Database, Event, Principal, Role, create_app, create_event_bus, require_roles

database = Database.from_settings()
get_db = database.get_db
bus = create_event_bus("analytics")

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/stats")
def stats(_: Principal = Depends(require_roles(Role.ADMIN))):
    # TODO(D3): aggregate from your own tables (never call the Incident DB).
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet (TASKS.md D3)")


@bus.consumer("analytics.events", ["incident.created", "incident.status_changed", "dispatch.assigned"])
def on_event(event: Event) -> None:
    # TODO(D3): upsert an IncidentFact row keyed by incident id. Must be idempotent: the same event can arrive twice.
    pass


app = create_app(service="analytics", title="DrukRescue Analytics", database=database, models_base=Base, bus=bus)
app.include_router(router)
