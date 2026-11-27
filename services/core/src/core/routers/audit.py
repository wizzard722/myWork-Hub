"""Auditlog inzien, controleren en exporteren (beheerders)."""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from core import audit
from core.audit import Actor, AuditEntry, RequestInfo
from core.deps import AdminDep, DbDep, PrincipalDep
from core.models import User

router = APIRouter(prefix="/audit", tags=["auditlog"])


class AuditOut(BaseModel):
    id: int
    occurred_at: datetime
    actor_type: str
    actor_id: uuid.UUID | None
    actor_email: str | None
    actor_role: str | None
    action: str
    outcome: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any]
    ip: str | None
    user_agent: str | None
    request_id: str | None
    hash: str

    model_config = {"from_attributes": True}


class AuditPage(BaseModel):
    items: list[AuditOut]
    next_before_id: int | None


class VerifyOut(BaseModel):
    valid: bool
    checked: int
    first_invalid_id: int | None


class AssistantEvent(BaseModel):
    action: str = Field(pattern=r"^assistant\.[a-z_.]{1,60}$")
    outcome: Literal["success", "denied", "failure"] = "success"
    target_type: str | None = Field(default=None, max_length=60)
    target_id: str | None = Field(default=None, max_length=200)
    details: dict[str, Any] = Field(default_factory=dict)


def _query(tenant_id, action, actor, outcome):
    query = select(AuditEntry).where(AuditEntry.tenant_id == tenant_id)
    if action:
        query = query.where(AuditEntry.action.startswith(action))
    if actor:
        query = query.where(AuditEntry.actor_email.ilike(f"%{actor}%"))
    if outcome:
        query = query.where(AuditEntry.outcome == outcome)
    return query


@router.get("", response_model=AuditPage)
async def list_audit(
    principal: AdminDep,
    db: DbDep,
    limit: int = Query(default=50, ge=1, le=500),
    before_id: int | None = Query(default=None, ge=1),
    action: str | None = Query(default=None, max_length=80),
    actor: str | None = Query(default=None, max_length=200),
    outcome: Literal["success", "denied", "failure"] | None = None,
) -> AuditPage:
    query = _query(principal.tenant_id, action, actor, outcome)
    if before_id:
        query = query.where(AuditEntry.id < before_id)
    async with db.tenant_session(principal.tenant_id) as session:
        rows = list(await session.scalars(query.order_by(AuditEntry.id.desc()).limit(limit + 1)))
    items = [AuditOut.model_validate(r) for r in rows[:limit]]
    return AuditPage(items=items, next_before_id=items[-1].id if len(rows) > limit else None)


@router.get("/verify", response_model=VerifyOut)
async def verify(principal: AdminDep, db: DbDep) -> VerifyOut:
    """Controleer of het auditlog van de klant onveranderd en compleet is."""
    async with db.tenant_session(principal.tenant_id) as session:
        result = await audit.verify_chain(session, principal.tenant_id)
    return VerifyOut(**result.__dict__)


@router.get("/export.csv", response_class=Response)
async def export_csv(
    request: Request,
    principal: AdminDep,
    db: DbDep,
    action: str | None = Query(default=None, max_length=80),
    actor: str | None = Query(default=None, max_length=200),
) -> Response:
    fields = list(AuditOut.model_fields)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(fields)
    async with db.tenant_session(principal.tenant_id) as session:
        query = _query(principal.tenant_id, action, actor, None).order_by(AuditEntry.id)
        count = 0
        for entry in await session.scalars(query):
            row = AuditOut.model_validate(entry).model_dump(mode="json")
            row["details"] = json.dumps(row["details"], ensure_ascii=False, sort_keys=True)
            writer.writerow([row[f] for f in fields])
            count += 1
        email = await session.scalar(select(User.email).where(User.id == principal.user_id))
        await audit.record(
            session,
            tenant_id=principal.tenant_id,
            actor=Actor.from_principal(principal, email),
            action="audit.exported",
            details={"rows": count, "filter": {"action": action, "actor": actor}},
            info=RequestInfo.from_request(request),
        )
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="auditlog.csv"'},
    )


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def assistant_event(
    body: AssistantEvent, request: Request, principal: PrincipalDep, db: DbDep
) -> dict:
    """Handeling van de assistent namens de ingelogde gebruiker vastleggen.

    De assistent stuurt het token van de gebruiker mee; de regel komt dus altijd op naam
    van die gebruiker, met ``actor_type = assistant``.
    """
    if db is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE)
    async with db.tenant_session(principal.tenant_id) as session:
        email = await session.scalar(select(User.email).where(User.id == principal.user_id))
        entry = await audit.record(
            session,
            tenant_id=principal.tenant_id,
            actor=Actor("assistant", principal.user_id, email, principal.role),
            action=body.action,
            outcome=body.outcome,
            target_type=body.target_type,
            target_id=body.target_id,
            details=body.details,
            info=RequestInfo.from_request(request),
        )
    return {"id": entry.id}
