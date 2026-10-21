"""Service-to-service REST clients."""

from __future__ import annotations

import os

import httpx

from drukcommon.auth import system_headers
from drukcommon.config import get_settings


def service_url(service: str) -> str:
    override = os.getenv(f"{service.upper().replace('-', '_')}_URL")
    return override or get_settings().service_url_template.format(service=service)


def service_client(service: str, timeout: float = 5.0) -> httpx.Client:
    """An httpx client for calling ``service`` as the current service (role SYSTEM)."""
    return httpx.Client(
        base_url=service_url(service),
        headers=system_headers(get_settings().service_name),
        timeout=timeout,
    )
