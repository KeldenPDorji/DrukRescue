from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from drukcommon.timeutil import utcnow


class Base(DeclarativeBase):
    pass


class Notification(Base):
    """One in-app message. Addressed to one user, to everyone with a role, or (both null) to everyone."""

    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("source_event_id", "recipient_key", name="uq_event_recipient"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    recipient_role: Mapped[str | None] = mapped_column(String(16), index=True)
    recipient_key: Mapped[str] = mapped_column(String(80))  # "user:<id>" | "role:<ROLE>" | "all"; for dedupe
    kind: Mapped[str] = mapped_column(String(16))  # INCIDENT | DISPATCH | ALERT
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(String(1000))
    incident_id: Mapped[str | None] = mapped_column(String(32))
    district: Mapped[str | None] = mapped_column(String(64))
    severity: Mapped[str | None] = mapped_column(String(16))
    source_event_id: Mapped[str] = mapped_column(String(64))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
