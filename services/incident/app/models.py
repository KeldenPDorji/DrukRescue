from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from drukcommon.timeutil import utcnow


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)  # INC-2026-001
    type: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    description: Mapped[str] = mapped_column(Text)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    district: Mapped[str | None] = mapped_column(String(64), index=True)
    location_name: Mapped[str | None] = mapped_column(String(128))
    photo_url: Mapped[str | None] = mapped_column(String(512))
    reporter_id: Mapped[str] = mapped_column(String(64), index=True)

    assigned_responder_id: Mapped[int | None] = mapped_column(Integer)
    assigned_responder_user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    assigned_responder_name: Mapped[str | None] = mapped_column(String(120))
    assigned_team: Mapped[str | None] = mapped_column(String(120))
    assigned_vehicle_id: Mapped[int | None] = mapped_column(Integer)
    assigned_vehicle_name: Mapped[str | None] = mapped_column(String(64))
    eta_minutes: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    timeline: Mapped[list[TimelineEntry]] = relationship(
        back_populates="incident", order_by="TimelineEntry.id", cascade="all, delete-orphan"
    )


class TimelineEntry(Base):
    """Every status change or progress update, for the citizen's tracking page and the audit trail."""

    __tablename__ = "incident_timeline"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    stage: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(String(500))
    actor_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="timeline")
