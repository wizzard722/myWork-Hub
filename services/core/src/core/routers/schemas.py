"""Gedeelde API-modellen."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["owner", "admin", "member"]


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class SessionOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut
    tenant: TenantOut


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)
    # Alleen nodig als de klant niet uit het subdomein of het account volgt (optioneel).
    tenant: str | None = Field(default=None, max_length=40)


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)
    role: Role = "member"


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=1, max_length=1024)


class MeUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class SignupIn(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=3, max_length=40)
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)


class TenantUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
