from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from drukcommon.timeutil import utcnow


class Base(DeclarativeBase):
    pass


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str] = mapped_column(String(255))
    profile_synced: Mapped[bool] = mapped_column(Boolean, default=True)  # False if the User service was down
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
