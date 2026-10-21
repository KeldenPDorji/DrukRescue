"""User service: profiles (name, phone, email, role, address). Credentials live in the auth service."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, Profile
from drukcommon import Database, Principal, Role, create_app, get_principal, require_roles
from drukcommon.timeutil import iso

database = Database.from_settings()
get_db = database.get_db


class ProfileCreate(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=32)
    role: Role = Role.CITIZEN
    address: str | None = Field(default=None, max_length=255)
    district: str | None = Field(default=None, max_length=64)


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=255)
    district: str | None = Field(default=None, max_length=64)


def to_out(p: Profile) -> dict:
    return {
        "id": p.id, "name": p.name, "email": p.email, "phone": p.phone, "role": p.role,
        "address": p.address, "district": p.district, "created_at": iso(p.created_at),
    }


def get_or_404(db: Session, user_id: str) -> Profile:
    p = db.get(Profile, user_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return p


router = APIRouter(prefix="/users", tags=["users"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create(body: ProfileCreate, _: Principal = Depends(require_roles(Role.SYSTEM, Role.ADMIN)),
           db: Session = Depends(get_db)):
    if body.role == Role.SYSTEM:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "SYSTEM is not a user role")
    p = Profile(**{**body.model_dump(), "id": body.id or str(uuid.uuid4()), "email": body.email.lower()})
    db.add(p)
    try:
        db.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with that id or email already exists") from None
    return to_out(p)


@router.get("")
def list_users(role: Role | None = None, limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0),
               _: Principal = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    q = select(Profile).order_by(Profile.created_at).limit(limit).offset(offset)
    if role:
        q = q.where(Profile.role == role)
    return [to_out(p) for p in db.scalars(q)]


@router.get("/me")
def get_me(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return to_out(get_or_404(db, principal.user_id))


@router.patch("/me")
def update_me(body: ProfileUpdate, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    p = get_or_404(db, principal.user_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(p, key, value)
    db.commit()
    return to_out(p)


@router.get("/{user_id}")
def get_one(user_id: str, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    if not principal.has(Role.ADMIN, Role.SYSTEM) and principal.user_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only view your own profile")
    return to_out(get_or_404(db, user_id))


app = create_app(service="user", title="DrukRescue User", database=database, models_base=Base)
app.include_router(router)
