"""Database access. One PostgreSQL, one schema + one DB user per service.

The connection sets ``search_path`` to the service's own schema, so tables are
created and queried there. The DB user only has rights on that schema (see
deploy/charts/platform/files/init-db.sh), so no service can read another's tables.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from drukcommon.config import get_settings

log = logging.getLogger(__name__)


class Database:
    def __init__(self, url: str, schema: str | None = None):
        if url.startswith("sqlite"):
            # Tests: one shared in-memory database across threads.
            self.engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
        else:
            connect_args = {"options": f"-csearch_path={schema}"} if schema else {}
            self.engine = create_engine(
                url, pool_pre_ping=True, pool_size=5, max_overflow=5, connect_args=connect_args
            )
        self.SessionLocal = sessionmaker(self.engine, expire_on_commit=False)

    @classmethod
    def from_settings(cls) -> Database:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL or DB_HOST must be set")
        return cls(settings.database_url, settings.db_schema)

    def create_all(self, base: type[DeclarativeBase], timeout_seconds: float = 60) -> None:
        """Create this service's tables, waiting for the DB to come up."""
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                base.metadata.create_all(self.engine)
                return
            except OperationalError:
                if time.monotonic() > deadline:
                    raise
                log.warning("database not reachable yet, retrying in 2s")
                time.sleep(2)

    def ping(self) -> bool:
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True

    @contextmanager
    def session(self) -> Iterator[Session]:
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def get_db(self) -> Iterator[Session]:
        """FastAPI dependency: ``db: Session = Depends(database.get_db)``."""
        with self.session() as db:
            yield db
