"""Configuration from environment variables (12-factor).

Kubernetes injects these from ConfigMaps/Secrets (see deploy/charts/drukrescue-lib);
docker-compose injects them from .env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import quote

from sqlalchemy.engine import URL


def env_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


def _database_url() -> str | None:
    if url := env_str("DATABASE_URL"):
        return url
    host = env_str("DB_HOST")
    if not host:
        return None
    return URL.create(
        "postgresql+psycopg",
        username=env_str("DB_USER"),
        password=env_str("DB_PASSWORD"),
        host=host,
        port=env_int("DB_PORT", 5432),
        database=env_str("DB_NAME", "drukrescue"),
    ).render_as_string(hide_password=False)


def _rabbitmq_url() -> str | None:
    if url := env_str("RABBITMQ_URL"):
        return url
    host = env_str("RABBITMQ_HOST")
    if not host:
        return None
    user = quote(env_str("RABBITMQ_USER", "guest"), safe="")
    password = quote(env_str("RABBITMQ_PASSWORD", "guest"), safe="")
    vhost = quote(env_str("RABBITMQ_VHOST", "/"), safe="")
    return f"amqp://{user}:{password}@{host}:{env_int('RABBITMQ_PORT', 5672)}/{vhost}"


def _redis_url() -> str | None:
    if url := env_str("REDIS_URL"):
        return url
    host = env_str("REDIS_HOST")
    if not host:
        return None
    password = env_str("REDIS_PASSWORD")
    auth = f":{quote(password, safe='')}@" if password else ""
    return f"redis://{auth}{host}:{env_int('REDIS_PORT', 6379)}/0"


@dataclass(frozen=True)
class Settings:
    service_name: str
    environment: str
    log_level: str
    database_url: str | None
    db_schema: str
    rabbitmq_url: str | None
    events_backend: str
    redis_url: str | None
    jwt_secret: str | None
    jwt_ttl_minutes: int
    service_url_template: str


@lru_cache
def get_settings() -> Settings:
    service = env_str("SERVICE_NAME", "unknown-service")
    rabbitmq_url = _rabbitmq_url()
    return Settings(
        service_name=service,
        environment=env_str("APP_ENV", "local"),
        log_level=env_str("LOG_LEVEL", "INFO").upper(),
        database_url=_database_url(),
        db_schema=env_str("DB_SCHEMA", service.replace("-", "_")),
        rabbitmq_url=rabbitmq_url,
        events_backend=env_str("EVENTS_BACKEND", "rabbitmq" if rabbitmq_url else "none"),
        redis_url=_redis_url(),
        jwt_secret=env_str("JWT_SECRET"),
        jwt_ttl_minutes=env_int("JWT_TTL_MINUTES", 480),
        # How services find each other. In Kubernetes and docker-compose the
        # Service name *is* the DNS name. Override one service with e.g. INCIDENT_URL.
        service_url_template=env_str("SERVICE_URL_TEMPLATE", "http://{service}:8000"),
    )
