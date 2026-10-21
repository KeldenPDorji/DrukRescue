"""Routing table and role-based access rules for the API Gateway.

Public URL                         -> upstream service, path forwarded as-is (minus "/api")
/api/incidents/INC-2026-001        -> http://incident:8000/incidents/INC-2026-001
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from drukcommon.auth import Role

# First path segment -> service name (Kubernetes Service / compose service).
ROUTES: dict[str, str] = {
    "auth": "auth",
    "users": "user",
    "incidents": "incident",
    "dispatch": "dispatch",
    "location": "location",
    "notifications": "notification",
    "responders": "responder",
    "vehicles": "vehicle",
    "shelters": "shelter",
    "resources": "resource",
    "alerts": "alert",
    "weather": "weather",
    "analytics": "analytics",
    "audit": "audit",
}

PUBLIC: set[tuple[str, str]] = {("POST", "/auth/register"), ("POST", "/auth/login")}

ALL_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
ADMIN = frozenset({Role.ADMIN})
NOBODY: frozenset[Role] = frozenset()


@dataclass(frozen=True)
class Rule:
    methods: frozenset[str]
    pattern: re.Pattern
    roles: frozenset[Role]  # empty = internal only, nobody from outside


def rule(methods, pattern: str, roles) -> Rule:
    return Rule(frozenset(methods), re.compile(pattern), frozenset(roles))


# First match wins. Anything not matched is open to any logged-in user;
# services still do their own fine-grained checks (defence in depth).
RULES: list[Rule] = [
    rule(ALL_METHODS, r"^/(responders|vehicles)/[^/]+/(claim|release)$", NOBODY),  # Dispatch only, in-cluster
    rule({"POST"}, r"^/users/?$", NOBODY),  # profiles are created by the auth service
    rule(ALL_METHODS, r"^/users/?$", ADMIN),
    rule(ALL_METHODS, r"^/auth/accounts", ADMIN),
    rule({"POST"}, r"^/incidents/[^/]+/(verify|redispatch)$", ADMIN),
    rule({"POST"}, r"^/incidents/[^/]+/progress$", {Role.RESPONDER, Role.ADMIN}),
    rule(ALL_METHODS, r"^/responders/me(/.*)?$", {Role.RESPONDER}),
    rule(ALL_METHODS, r"^/(responders|vehicles)(/.*)?$", ADMIN),
    rule(WRITE_METHODS, r"^/(shelters|resources|alerts)(/.*)?$", ADMIN),
    rule(ALL_METHODS, r"^/(audit|analytics|dispatch)(/.*)?$", ADMIN),
]


def resolve_service(path: str) -> str | None:
    segment = path.strip("/").split("/", 1)[0]
    return ROUTES.get(segment)


def is_public(method: str, path: str) -> bool:
    return (method, path.rstrip("/")) in PUBLIC


def allowed_roles(method: str, path: str) -> frozenset[Role] | None:
    """Roles allowed for this request, or None if any authenticated user may proceed."""
    for r in RULES:
        if method in r.methods and r.pattern.search(path):
            return r.roles
    return None
