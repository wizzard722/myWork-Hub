"""Auditlog: elke beheer- en beveiligingshandeling is te herleiden.

Elke regel legt vast wie (gebruiker, rol of systeem/assistent), wat (actie, doel,
details), wanneer, waarvandaan (IP, user-agent, request-id) en met welke uitkomst.

- **Onveranderbaar:** de applicatie mag alleen toevoegen en lezen (GRANT), en een
  trigger blokkeert UPDATE en DELETE.
- **Hash-keten per klant:** elke regel bevat de hash van de vorige; wijzigen of
  weglaten van een regel is te detecteren met ``verify_chain``.
- **Zelfde transactie:** een handeling en de bijbehorende auditregel worden samen
  opgeslagen; mislukt het een, dan het ander ook.
- Elke regel gaat daarnaast als JSON naar de logger ``audit`` (voor een SIEM).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from fastapi import Request
from sqlalchemy import BigInteger, DateTime, String, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from core.models import Base
from core.security import Principal

log = logging.getLogger("audit")

Outcome = Literal["success", "denied", "failure"]
ActorType = Literal["user", "assistant", "system"]
PLATFORM_LOCK = "mywork-audit-platform"


class AuditEntry(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_type: Mapped[str] = mapped_column(String)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_email: Mapped[str | None] = mapped_column(String)
    actor_role: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    outcome: Mapped[str] = mapped_column(String)
    target_type: Mapped[str | None] = mapped_column(String)
    target_id: Mapped[str | None] = mapped_column(String)
    details: Mapped[dict] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String)
    user_agent: Mapped[str | None] = mapped_column(String)
    request_id: Mapped[str | None] = mapped_column(String)
    prev_hash: Mapped[str | None] = mapped_column(String)
    hash: Mapped[str] = mapped_column(String)


@dataclass
class Actor:
    type: ActorType = "user"
    id: uuid.UUID | None = None
    email: str | None = None
    role: str | None = None

    @classmethod
    def from_principal(cls, principal: Principal, email: str | None = None) -> Actor:
        return cls("user", principal.user_id, email, principal.role)

    @classmethod
    def system(cls, name: str) -> Actor:
        return cls("system", None, name, None)


@dataclass
class RequestInfo:
    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_request(cls, request: Request) -> RequestInfo:
        # X-Real-IP zet de gateway uit het vertrouwde X-Forwarded-For (realip-module);
        # alleen de gateway kan de core bereiken.
        ip = request.headers.get("x-real-ip") or (request.client.host if request.client else None)
        return cls(
            ip=ip,
            user_agent=(request.headers.get("user-agent") or "")[:300] or None,
            request_id=request.headers.get("x-request-id"),
        )


def _canonical(entry: dict[str, Any]) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str)


def _hash(prev_hash: str | None, payload: dict[str, Any]) -> str:
    return hashlib.sha256(((prev_hash or "") + _canonical(payload)).encode()).hexdigest()


def _payload(entry: AuditEntry) -> dict[str, Any]:
    return {
        "tenant_id": str(entry.tenant_id) if entry.tenant_id else None,
        "occurred_at": entry.occurred_at.isoformat(),
        "actor_type": entry.actor_type,
        "actor_id": str(entry.actor_id) if entry.actor_id else None,
        "actor_email": entry.actor_email,
        "actor_role": entry.actor_role,
        "action": entry.action,
        "outcome": entry.outcome,
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "details": entry.details,
        "ip": entry.ip,
        "user_agent": entry.user_agent,
        "request_id": entry.request_id,
    }


async def record(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None,
    actor: Actor,
    action: str,
    outcome: Outcome = "success",
    target_type: str | None = None,
    target_id: str | uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    info: RequestInfo | None = None,
) -> AuditEntry:
    """Voeg een regel toe aan het auditlog, in de transactie van ``session``."""
    info = info or RequestInfo()
    # Eén schrijver tegelijk per klant, zodat de hash-keten klopt.
    lock_key = str(tenant_id) if tenant_id else PLATFORM_LOCK
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": lock_key})
    prev_hash = await session.scalar(
        select(AuditEntry.hash)
        .where(AuditEntry.tenant_id == tenant_id if tenant_id else AuditEntry.tenant_id.is_(None))
        .order_by(AuditEntry.id.desc())
        .limit(1)
    )
    now = await session.scalar(text("SELECT clock_timestamp()"))
    entry = AuditEntry(
        tenant_id=tenant_id,
        occurred_at=now,
        actor_type=actor.type,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_role=actor.role,
        action=action,
        outcome=outcome,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details or {},
        ip=info.ip,
        user_agent=info.user_agent,
        request_id=info.request_id,
        prev_hash=prev_hash,
    )
    entry.hash = _hash(prev_hash, _payload(entry))
    session.add(entry)
    await session.flush()
    log.info(_canonical({**_payload(entry), "id": entry.id, "hash": entry.hash}))
    return entry


@dataclass
class VerifyResult:
    valid: bool
    checked: int
    first_invalid_id: int | None = None


async def verify_chain(session: AsyncSession, tenant_id: uuid.UUID) -> VerifyResult:
    """Controleer de hash-keten van een klant van begin tot eind."""
    prev: str | None = None
    checked = 0
    rows = await session.stream_scalars(
        select(AuditEntry).where(AuditEntry.tenant_id == tenant_id).order_by(AuditEntry.id)
    )
    async for entry in rows:
        checked += 1
        if entry.prev_hash != prev or entry.hash != _hash(prev, _payload(entry)):
            return VerifyResult(False, checked, entry.id)
        prev = entry.hash
    return VerifyResult(True, checked)
