"""TEMPLATE service. Copy this folder to start a new service (see services/_template/README.md).

You get /healthz, /readyz, /metrics, JSON logs with trace ids and OpenTelemetry traces from create_app().
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from drukcommon import Principal, create_app, get_principal

# Uncomment what your service needs:
# from drukcommon import Database, create_event_bus
# from app.models import Base
# database = Database.from_settings()      # own schema, own DB user
# get_db = database.get_db                 # db: Session = Depends(get_db)
# bus = create_event_bus("template")       # bus.publish(...), @bus.consumer(...)

router = APIRouter(prefix="/template", tags=["template"])


@router.get("/hello")
def hello(principal: Principal = Depends(get_principal)):
    return {"hello": principal.user_id, "role": principal.role}


app = create_app(service="template", title="DrukRescue Template")  # add database=..., models_base=Base, bus=bus
app.include_router(router)
