"""Auth service: register, login, and issue JWTs carrying the user's role.

- Public registration always creates a CITIZEN.
- RESPONDER and ADMIN accounts are created by an admin (POST /auth/accounts).
- The first admin comes from BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD (a Kubernetes Secret).
"""

from __future__ import annotations

import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, Credential
from app.passwords import DUMMY_HASH, hash_password, verify_password
from drukcommon import Database, Principal, Role, create_app, get_principal, get_settings, require_roles
from drukcommon.auth import create_access_token, require_jwt_secret
from drukcommon.config import env_str
from drukcommon.http import service_client

log = logging.getLogger("auth")
settings = get_settings()
JWT_SECRET = require_jwt_secret(settings.jwt_secret)  # fail fast at startup if missing

database = Database.from_settings()
get_db = database.get_db


def user_client() -> httpx.Client:
    return service_client("user")


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class AccountRequest(RegisterRequest):
    role: Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


def token_response(cred: Credential) -> dict:
    token = create_access_token(
        user_id=cred.user_id, role=Role(cred.role), name=cred.name,
        secret=JWT_SECRET, ttl_minutes=settings.jwt_ttl_minutes,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.jwt_ttl_minutes * 60,
        "user": {"id": cred.user_id, "name": cred.name, "email": cred.email, "role": cred.role},
    }


def create_profile(user_id: str, name: str, email: str, phone: str | None, role: Role) -> None:
    """Create the matching profile in the User service. Raises HTTPException on failure."""
    try:
        with user_client() as client:
            res = client.post("/users", json={"id": user_id, "name": name, "email": email, "phone": phone, "role": role})
    except httpx.HTTPError:
        log.exception("user service unreachable")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "User service unavailable, try again") from None
    if res.status_code == 409:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    if res.status_code >= 400:
        log.error("user service rejected profile", extra={"status": res.status_code})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not create user profile")


def create_account(db: Session, body: RegisterRequest, role: Role) -> Credential:
    email = body.email.lower()
    if db.scalar(select(Credential).where(Credential.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user_id = str(uuid.uuid4())
    create_profile(user_id, body.name, email, body.phone, role)
    cred = Credential(user_id=user_id, email=email, name=body.name, role=role, password_hash=hash_password(body.password))
    db.add(cred)
    try:
        db.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    log.info("account created", extra={"user_id": user_id, "role": role})
    return cred


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    return token_response(create_account(db, body, Role.CITIZEN))


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    cred = db.scalar(select(Credential).where(Credential.email == body.email.lower()))
    if not verify_password(body.password, cred.password_hash if cred else DUMMY_HASH) or cred is None:
        log.info("login failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not cred.profile_synced:
        _try_sync_profile(db, cred)
    return token_response(cred)


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_staff_account(body: AccountRequest, _: Principal = Depends(require_roles(Role.ADMIN)),
                         db: Session = Depends(get_db)):
    if body.role == Role.SYSTEM:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "SYSTEM is not a user role")
    cred = create_account(db, body, body.role)
    return {"id": cred.user_id, "name": cred.name, "email": cred.email, "role": cred.role}


@router.get("/me")
def me(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    cred = db.scalar(select(Credential).where(Credential.user_id == principal.user_id))
    if cred is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return {"id": cred.user_id, "name": cred.name, "email": cred.email, "role": cred.role}


def _try_sync_profile(db: Session, cred: Credential) -> None:
    try:
        create_profile(cred.user_id, cred.name, cred.email, None, Role(cred.role))
    except HTTPException as exc:
        if exc.status_code != status.HTTP_409_CONFLICT:
            log.warning("profile still not synced", extra={"user_id": cred.user_id})
            return
    cred.profile_synced = True
    db.commit()


def bootstrap_admin() -> None:
    email, password = env_str("BOOTSTRAP_ADMIN_EMAIL"), env_str("BOOTSTRAP_ADMIN_PASSWORD")
    if not email or not password:
        return
    with database.session() as db:
        if db.scalar(select(Credential).where(Credential.email == email.lower())):
            return
        cred = Credential(user_id=str(uuid.uuid4()), email=email.lower(), name="Command Centre Admin",
                          role=Role.ADMIN, password_hash=hash_password(password), profile_synced=False)
        db.add(cred)
        db.commit()
        log.info("bootstrap admin created", extra={"user_id": cred.user_id})
        _try_sync_profile(db, cred)  # the User service may not be up yet; retried on first login


app = create_app(service="auth", title="DrukRescue Auth", database=database, models_base=Base,
                 on_startup=[bootstrap_admin])
app.include_router(router)
