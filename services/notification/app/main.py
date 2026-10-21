"""Notification service: listens to events and creates in-app notifications for citizens, responders and admins.

Real SMS/push would plug in behind this same service; the frontend polls GET /notifications/me.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.messages import drafts_for
from app.models import Base, Notification
from drukcommon import Database, Event, Principal, create_app, create_event_bus, get_principal
from drukcommon.timeutil import iso, utcnow

log = logging.getLogger("notification")

database = Database.from_settings()
get_db = database.get_db
bus = create_event_bus("notification")


def to_out(n: Notification) -> dict:
    return {
        "id": n.id, "kind": n.kind, "title": n.title, "message": n.message, "incident_id": n.incident_id,
        "district": n.district, "severity": n.severity, "personal": n.recipient_user_id is not None,
        "read": n.read_at is not None, "created_at": iso(n.created_at),
    }


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/me")
def my_notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    q = (
        select(Notification)
        .where(or_(
            Notification.recipient_user_id == principal.user_id,
            Notification.recipient_role == principal.role.value,
            Notification.recipient_key == "all",
        ))
        .order_by(Notification.id.desc())
        .limit(limit)
    )
    if unread_only:
        q = q.where(Notification.read_at.is_(None), Notification.recipient_user_id == principal.user_id)
    return [to_out(n) for n in db.scalars(q)]


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if n is None or n.recipient_user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    n.read_at = n.read_at or utcnow()
    db.commit()
    return to_out(n)


@bus.consumer("notification.events", ["incident.created", "incident.status_changed", "dispatch.assigned", "alert.issued"])
def on_event(event: Event) -> None:
    drafts = [d for d in drafts_for(event.type, event.data) if d.user_id or d.role or d.kind == "ALERT"]
    if not drafts:
        return
    with database.session() as db:
        for d in drafts:
            db.add(Notification(
                recipient_user_id=d.user_id, recipient_role=d.role, recipient_key=d.recipient_key, kind=d.kind,
                title=d.title[:200], message=d.message[:1000], incident_id=d.incident_id, district=d.district,
                severity=d.severity, source_event_id=event.id,
            ))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # same event delivered twice: already stored
            log.info("duplicate event ignored", extra={"event_id": event.id})
            return
    log.info("notifications created", extra={"event_type": event.type, "count": len(drafts)})


app = create_app(service="notification", title="DrukRescue Notification", database=database, models_base=Base, bus=bus)
app.include_router(router)
