"""API Gateway: the single entry point.

For every request to /api/<resource>/...:
  1. pick the upstream service from the first path segment   (rules.ROUTES)
  2. verify the JWT (except register/login)                  -> 401
  3. check the caller's role against RULES                   -> 403
  4. rate-limit per user (or per IP for login/register)      -> 429
  5. strip any client-sent X-User-* headers, add trusted ones, forward
"""

from __future__ import annotations

import logging
import uuid

import httpx
import jwt
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.ratelimit import RateLimiter
from app.rules import allowed_roles, is_public, resolve_service
from drukcommon import Role, create_app, get_settings
from drukcommon.auth import USER_ID_HEADER, USER_ROLE_HEADER, decode_access_token, require_jwt_secret
from drukcommon.config import env_bool, env_float, env_int, env_str
from drukcommon.http import service_url

log = logging.getLogger("gateway")
settings = get_settings()
JWT_SECRET = require_jwt_secret(settings.jwt_secret)

RATE_LIMIT_PER_MINUTE = env_int("RATE_LIMIT_PER_MINUTE", 120)
AUTH_RATE_LIMIT_PER_MINUTE = env_int("AUTH_RATE_LIMIT_PER_MINUTE", 10)
MAX_BODY_BYTES = env_int("MAX_BODY_BYTES", 1_000_000)

limiter = RateLimiter(settings.redis_url, enabled=env_bool("RATE_LIMIT_ENABLED", True))
upstream = httpx.AsyncClient(timeout=env_float("UPSTREAM_TIMEOUT_SECONDS", 10.0), follow_redirects=False)

# Never forwarded upstream. Identity headers are stripped so clients can't forge them.
DROP_REQUEST_HEADERS = {
    "host", "content-length", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade", "authorization", "cookie",
    USER_ID_HEADER.lower(), USER_ROLE_HEADER.lower(),
}
DROP_RESPONSE_HEADERS = {"content-length", "content-encoding", "transfer-encoding", "connection", "keep-alive"}


def error(status: int, detail: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status, headers=headers)


def client_ip(request: Request) -> str:
    # ingress-nginx (and our frontend nginx) overwrite X-Real-IP with the real client address.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def bearer_token(request: Request) -> str | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


async def shutdown() -> None:
    await upstream.aclose()
    await limiter.close()


app = create_app(service="gateway", title="DrukRescue API Gateway", on_shutdown=[shutdown])

if origins := env_str("CORS_ORIGINS"):  # only needed when the frontend runs on another origin (local dev)
    app.add_middleware(CORSMiddleware, allow_origins=origins.split(","), allow_methods=["*"],
                       allow_headers=["Authorization", "Content-Type"])


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request) -> Response:
    path = "/" + path
    method = request.method
    if any(segment in {".", ".."} for segment in path.split("/")):
        return error(400, "Invalid path")
    service = resolve_service(path)
    if service is None:
        return error(404, "Unknown API route")

    user_id: str | None = None
    role: Role | None = None
    if not is_public(method, path):
        token = bearer_token(request)
        if token is None:
            return error(401, "Missing bearer token", {"WWW-Authenticate": "Bearer"})
        try:
            claims = decode_access_token(token, JWT_SECRET)
        except jwt.ExpiredSignatureError:
            return error(401, "Token expired", {"WWW-Authenticate": "Bearer"})
        except jwt.InvalidTokenError:
            return error(401, "Invalid token", {"WWW-Authenticate": "Bearer"})
        user_id, role = claims["sub"], Role(claims["role"])
        roles = allowed_roles(method, path)
        if roles is not None and role not in roles:
            log.info("forbidden", extra={"user_id": user_id, "role": role, "method": method, "path": path})
            return error(403, "Your role cannot do this")

    if user_id:
        key, limit = f"user:{user_id}", RATE_LIMIT_PER_MINUTE
    else:
        key, limit = f"ip:{client_ip(request)}", AUTH_RATE_LIMIT_PER_MINUTE
    allowed, retry_after = await limiter.hit(key, limit)
    if not allowed:
        return error(429, "Too many requests", {"Retry-After": str(retry_after)})

    if int(request.headers.get("content-length") or 0) > MAX_BODY_BYTES:
        return error(413, "Request body too large")
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return error(413, "Request body too large")

    headers = {k: v for k, v in request.headers.items() if k.lower() not in DROP_REQUEST_HEADERS}
    headers["X-Request-Id"] = request.headers.get("x-request-id") or uuid.uuid4().hex
    headers["X-Forwarded-For"] = client_ip(request)
    if user_id and role:
        headers[USER_ID_HEADER] = user_id
        headers[USER_ROLE_HEADER] = role.value

    try:
        resp = await upstream.request(method, f"{service_url(service)}{path}",
                                      params=request.query_params.multi_items(), content=body, headers=headers)
    except httpx.TimeoutException:
        log.warning("upstream timeout", extra={"upstream": service, "path": path})
        return error(504, f"{service} service timed out")
    except httpx.HTTPError:
        log.warning("upstream unavailable", extra={"upstream": service, "path": path})
        return error(502, f"{service} service unavailable")

    out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in DROP_RESPONSE_HEADERS}
    return Response(content=resp.content, status_code=resp.status_code, headers=out_headers)
