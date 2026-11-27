"""Gebruikersbeheer binnen de eigen klant (beheerders)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response, status

from core import accounts
from core.audit import RequestInfo
from core.deps import AdminDep, DbDep
from core.routers.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["gebruikers"])


@router.get("", response_model=list[UserOut])
async def list_users(principal: AdminDep, db: DbDep) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in await accounts.list_users(db, principal.tenant_id)]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate, request: Request, principal: AdminDep, db: DbDep
) -> UserOut:
    user = await accounts.create_user(
        db,
        principal,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        role=body.role,
        info=RequestInfo.from_request(request),
    )
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, request: Request, principal: AdminDep, db: DbDep
) -> UserOut:
    user = await accounts.update_user(
        db,
        principal,
        user_id,
        **body.model_dump(exclude_unset=True),
        info=RequestInfo.from_request(request),
    )
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID, request: Request, principal: AdminDep, db: DbDep
) -> Response:
    await accounts.delete_user(db, principal, user_id, RequestInfo.from_request(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
