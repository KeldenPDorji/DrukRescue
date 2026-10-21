"""Identity inside the cluster.

Only the API Gateway validates JWTs. It then forwards the caller's identity as
``X-User-Id`` / ``X-User-Role`` headers (after stripping any the client sent).
Services trust those headers because NetworkPolicy only lets the gateway (and
named internal callers) reach them.

Service-to-service calls identify themselves with role ``SYSTEM``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import jwt
from fastapi import Depends, HTTPException, Request, status

USER_ID_HEADER = "X-User-Id"
USER_ROLE_HEADER = "X-User-Role"
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "drukrescue-auth"


class Role(StrEnum):
    CITIZEN = "CITIZEN"
    RESPONDER = "RESPONDER"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"  # internal service-to-service calls only; never issued in a JWT


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: Role

    def has(self, *roles: Role) -> bool:
        return self.role in roles


def get_principal(request: Request) -> Principal:
    user_id = request.headers.get(USER_ID_HEADER)
    role = request.headers.get(USER_ROLE_HEADER)
    if not user_id or not role:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing identity headers (call through the API gateway)")
    try:
        return Principal(user_id=user_id, role=Role(role))
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Unknown role {role!r}") from None


def require_roles(*roles: Role):
    """FastAPI dependency: ``principal: Principal = Depends(require_roles(Role.ADMIN))``."""

    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return principal

    return dependency


def system_headers(service: str) -> dict[str, str]:
    return {USER_ID_HEADER: f"system:{service}", USER_ROLE_HEADER: Role.SYSTEM.value}


# --- JWT (used by the auth service to issue and the gateway to verify) ---------------------


def require_jwt_secret(secret: str | None) -> str:
    if not secret or len(secret) < 32:
        raise RuntimeError("JWT_SECRET must be set and at least 32 characters long")
    return secret


def create_access_token(*, user_id: str, role: Role, name: str, secret: str, ttl_minutes: int) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "role": role.value,
        "name": name,
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(claims, require_jwt_secret(secret), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret: str) -> dict:
    """Raises jwt.InvalidTokenError on a bad, expired or tampered token."""
    claims = jwt.decode(
        token,
        require_jwt_secret(secret),
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        options={"require": ["exp", "sub", "iss"]},
    )
    if claims.get("role") not in {Role.CITIZEN, Role.RESPONDER, Role.ADMIN}:
        raise jwt.InvalidTokenError("invalid role claim")
    return claims
