"""Alert service (SCAFFOLD, see TASKS.md B1).

Area-wide warnings (title, message, district, severity, expiry), issued by the command centre.
On issue it publishes ``alert.issued``. The Notification service already consumes it,
so every user sees the alert as soon as you publish the event with the right payload.
The spec and acceptance criteria are in services/alert/README.md; the event contract is in docs/events.md.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.models import Base
from drukcommon import Database, Principal, create_app, create_event_bus, get_principal

database = Database.from_settings()
get_db = database.get_db
bus = create_event_bus("alert")

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def list_alerts(principal: Principal = Depends(get_principal)):
    # TODO(B1): list alerts; ?district= and ?active=true (not expired, not cancelled).
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet (TASKS.md B1)")


# TODO(B1): POST /alerts (ADMIN): save, commit, then bus.publish("alert.issued", {...})
#           (commit first, publish second, like services/incident/app/main.py)
# TODO(B1): GET /alerts/{id}, POST /alerts/{id}/cancel (ADMIN)

app = create_app(service="alert", title="DrukRescue Alert", database=database, models_base=Base, bus=bus)
app.include_router(router)
