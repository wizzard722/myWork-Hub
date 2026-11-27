"""Klanten, gebruikers en inlogsessies (servicelaag, zonder HTTP).

Elke wijziging schrijft in dezelfde transactie een regel in het auditlog (core.audit).
Geweigerde handelingen worden apart vastgelegd (``record_denied``), omdat de transactie
van de handeling zelf dan wordt teruggedraaid.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core import audit
from core.audit import Actor, RequestInfo
from core.db import Database
from core.models import RefreshToken, Tenant, User
from core.security import (
    MIN_PASSWORD_LENGTH,
    Principal,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    new_refresh_token,
    verify_password,
)
from core.tenancy import valid_slug


class AccountError(Exception):
    """Fout die als nette melding naar de gebruiker mag."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_email(email: str) -> str:
    return email.strip().lower()


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AccountError(f"Wachtwoord moet minimaal {MIN_PASSWORD_LENGTH} tekens hebben")


async def _actor(session: AsyncSession, principal: Principal) -> Actor:
    email = await session.scalar(select(User.email).where(User.id == principal.user_id))
    return Actor.from_principal(principal, email)


async def record_denied(
    db: Database,
    principal: Principal,
    action: str,
    reason: str,
    info: RequestInfo | None,
    target_type: str | None = None,
    target_id: Any = None,
) -> None:
    """Leg een geweigerde handeling vast (in een eigen transactie)."""
    async with db.tenant_session(principal.tenant_id) as session:
        await audit.record(
            session,
            tenant_id=principal.tenant_id,
            actor=await _actor(session, principal),
            action=action,
            outcome="denied",
            target_type=target_type,
            target_id=target_id,
            details={"reason": reason},
            info=info,
        )


# --- Klanten -------------------------------------------------------------------------


async def create_tenant(
    db: Database,
    *,
    slug: str,
    name: str,
    owner_email: str,
    owner_password: str,
    owner_name: str,
    actor: Actor | None = None,
    info: RequestInfo | None = None,
) -> tuple[Tenant, User]:
    slug = slug.strip().lower()
    if not valid_slug(slug):
        raise AccountError("Ongeldige klantnaam voor het subdomein")
    check_password(owner_password)
    actor = actor or Actor.system("onbekend")
    async with db.system_session() as session:
        tenant = Tenant(slug=slug, name=name.strip())
        session.add(tenant)
        try:
            await session.flush()
        except IntegrityError:
            raise AccountError("Deze klantnaam is al in gebruik", 409) from None
        owner = await _insert_user(
            session,
            tenant_id=tenant.id,
            email=owner_email,
            password=owner_password,
            display_name=owner_name,
            role="owner",
        )
        common = {"tenant_id": tenant.id, "actor": actor, "info": info}
        await audit.record(
            session,
            **common,
            action="tenant.created",
            target_type="tenant",
            target_id=tenant.id,
            details={"slug": slug, "name": tenant.name},
        )
        await audit.record(
            session,
            **common,
            action="user.created",
            target_type="user",
            target_id=owner.id,
            details={"email": owner.email, "role": "owner"},
        )
    return tenant, owner


async def get_tenant_by_slug(db: Database, slug: str) -> Tenant | None:
    async with db.system_session() as session:
        return await session.scalar(select(Tenant).where(Tenant.slug == slug))


async def rename_tenant(
    db: Database, principal: Principal, name: str, info: RequestInfo | None = None
) -> Tenant:
    if principal.role != "owner":
        await record_denied(db, principal, "tenant.updated", "alleen eigenaren", info)
        raise AccountError("Alleen voor eigenaren", 403)
    # Tenants zijn alleen in systeemcontext te wijzigen (RLS); beperkt tot de eigen klant.
    async with db.system_session() as session:
        tenant = await session.get(Tenant, principal.tenant_id, with_for_update=True)
        old = tenant.name
        tenant.name = name.strip()
        await audit.record(
            session,
            tenant_id=tenant.id,
            actor=await _actor(session, principal),
            action="tenant.updated",
            target_type="tenant",
            target_id=tenant.id,
            details={"name": [old, tenant.name]},
            info=info,
        )
    return tenant


# --- Gebruikers ----------------------------------------------------------------------


async def _insert_user(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    email: str,
    password: str,
    display_name: str,
    role: str,
) -> User:
    check_password(password)
    user = User(
        tenant_id=tenant_id,
        email=normalize_email(email),
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        role=role,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        raise AccountError("Er bestaat al een account met dit e-mailadres", 409) from None
    await session.refresh(user)
    return user


async def create_user(
    db: Database,
    actor: Principal,
    *,
    email: str,
    password: str,
    display_name: str,
    role: str,
    info: RequestInfo | None = None,
) -> User:
    if role == "owner" and actor.role != "owner":
        await record_denied(db, actor, "user.created", "alleen eigenaren maken eigenaren", info)
        raise AccountError("Alleen een eigenaar kan een eigenaar toevoegen", 403)
    async with db.tenant_session(actor.tenant_id) as session:
        user = await _insert_user(
            session,
            tenant_id=actor.tenant_id,
            email=email,
            password=password,
            display_name=display_name,
            role=role,
        )
        await audit.record(
            session,
            tenant_id=actor.tenant_id,
            actor=await _actor(session, actor),
            action="user.created",
            target_type="user",
            target_id=user.id,
            details={"email": user.email, "display_name": user.display_name, "role": role},
            info=info,
        )
        return user


async def list_users(db: Database, tenant_id: uuid.UUID) -> list[User]:
    async with db.tenant_session(tenant_id) as session:
        result = await session.scalars(select(User).order_by(User.display_name))
        return list(result)


async def get_user(db: Database, tenant_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
    async with db.tenant_session(tenant_id) as session:
        return await session.get(User, user_id)


async def _active_owner_count(session: AsyncSession) -> int:
    return await session.scalar(
        select(func.count()).select_from(User).where(User.role == "owner", User.is_active)
    )


def _update_action(changes: dict[str, Any]) -> str:
    if "role" in changes:
        return "user.role_changed"
    if "is_active" in changes:
        return "user.activated" if changes["is_active"][1] else "user.deactivated"
    if "password" in changes:
        return "user.password_reset"
    return "user.updated"


async def update_user(
    db: Database,
    actor: Principal,
    user_id: uuid.UUID,
    *,
    display_name: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    password: str | None = None,
    info: RequestInfo | None = None,
) -> User:
    # Controle en wijziging in één vergrendelde transactie. Bij een weigering wordt
    # alleen de auditregel opgeslagen en daarna pas de fout gegeven.
    error: tuple[str, int] | None = None
    async with db.tenant_session(actor.tenant_id) as session:
        user = await session.get(User, user_id, with_for_update=True)
        if user is None:
            raise AccountError("Gebruiker niet gevonden", 404)
        touches_owner = user.role == "owner" or role == "owner"
        loses_owner = user.role == "owner" and (
            (role is not None and role != "owner") or is_active is False
        )
        if touches_owner and actor.role != "owner":
            error = ("Alleen een eigenaar kan eigenaren wijzigen", 403)
        elif loses_owner and await _active_owner_count(session) <= 1:
            error = ("Er moet minimaal één actieve eigenaar blijven", 409)
        elif user.id == actor.user_id and (is_active is False or (role and role != user.role)):
            error = ("Je kunt je eigen rol of account niet uitschakelen", 409)
        if password is not None and error is None:
            check_password(password)
        if error:
            await audit.record(
                session,
                tenant_id=actor.tenant_id,
                actor=await _actor(session, actor),
                action="user.updated",
                outcome="denied",
                target_type="user",
                target_id=user.id,
                details={"reason": error[0], "email": user.email},
                info=info,
            )
        else:
            changes: dict[str, Any] = {}
            if display_name is not None and display_name.strip() != user.display_name:
                changes["display_name"] = [user.display_name, display_name.strip()]
                user.display_name = display_name.strip()
            if role is not None and role != user.role:
                changes["role"] = [user.role, role]
                user.role = role
            if is_active is not None and is_active != user.is_active:
                changes["is_active"] = [user.is_active, is_active]
                user.is_active = is_active
            if password is not None:
                user.password_hash = hash_password(password)
                changes["password"] = "gewijzigd"
            if is_active is False or password is not None:
                await _revoke_user_tokens(session, user.id)
            await session.flush()
            await session.refresh(user)
            if changes:
                await audit.record(
                    session,
                    tenant_id=actor.tenant_id,
                    actor=await _actor(session, actor),
                    action=_update_action(changes),
                    target_type="user",
                    target_id=user.id,
                    details={"email": user.email, "changes": changes},
                    info=info,
                )
    if error:
        raise AccountError(*error)
    return user


async def delete_user(
    db: Database, actor: Principal, user_id: uuid.UUID, info: RequestInfo | None = None
) -> None:
    async with db.tenant_session(actor.tenant_id) as session:
        user = await session.get(User, user_id, with_for_update=True)
        if user is None:
            raise AccountError("Gebruiker niet gevonden", 404)
        if user.id == actor.user_id:
            error = ("Je kunt je eigen account niet verwijderen", 409)
        elif user.role == "owner" and actor.role != "owner":
            error = ("Alleen een eigenaar kan eigenaren verwijderen", 403)
        elif user.role == "owner" and await _active_owner_count(session) <= 1:
            error = ("Er moet minimaal één actieve eigenaar blijven", 409)
        else:
            error = None
        if error:
            await audit.record(
                session,
                tenant_id=actor.tenant_id,
                actor=await _actor(session, actor),
                action="user.deleted",
                outcome="denied",
                target_type="user",
                target_id=user.id,
                details={"reason": error[0], "email": user.email},
                info=info,
            )
        else:
            await audit.record(
                session,
                tenant_id=actor.tenant_id,
                actor=await _actor(session, actor),
                action="user.deleted",
                target_type="user",
                target_id=user.id,
                details={"email": user.email, "display_name": user.display_name, "role": user.role},
                info=info,
            )
            await session.delete(user)
    if error:
        raise AccountError(*error)


async def change_own_password(
    db: Database,
    principal: Principal,
    current_password: str,
    new_password: str,
    info: RequestInfo | None = None,
) -> None:
    async with db.tenant_session(principal.tenant_id) as session:
        user = await session.get(User, principal.user_id, with_for_update=True)
        ok = user is not None and verify_password(user.password_hash, current_password)
    if not ok:
        await record_denied(db, principal, "user.password_changed", "huidig wachtwoord fout", info)
        raise AccountError("Huidig wachtwoord klopt niet", 400)
    check_password(new_password)
    async with db.tenant_session(principal.tenant_id) as session:
        user = await session.get(User, principal.user_id, with_for_update=True)
        user.password_hash = hash_password(new_password)
        await _revoke_user_tokens(session, user.id)
        await audit.record(
            session,
            tenant_id=principal.tenant_id,
            actor=Actor.from_principal(principal, user.email),
            action="user.password_changed",
            target_type="user",
            target_id=user.id,
            info=info,
        )


# --- Inloggen en sessies -------------------------------------------------------------


@dataclass
class LoginResult:
    principal: Principal
    refresh_token: str
    user: User
    tenant: Tenant


async def authenticate(
    db: Database,
    *,
    email: str,
    password: str,
    tenant_slug: str | None,
    info: RequestInfo | None = None,
) -> tuple[User, Tenant] | None:
    """Controleer e-mail en wachtwoord en leg elke poging vast in het auditlog.

    De klant volgt uit het account. Komt de aanvraag binnen op een subdomein, dan moet
    het account bij die klant horen.
    """
    email = normalize_email(email)
    async with db.system_session() as session:
        row = (
            await session.execute(
                select(User, Tenant)
                .join(Tenant, Tenant.id == User.tenant_id)
                .where(User.email == email)
            )
        ).first()
        user, tenant = (row[0], row[1]) if row else (None, None)
        valid = verify_password(user.password_hash if user else None, password)
        reason = None
        if user is None or tenant is None:
            reason = "onbekend e-mailadres"
        elif not valid:
            reason = "wachtwoord onjuist"
        elif not user.is_active:
            reason = "account uitgeschakeld"
        elif tenant.status != "active":
            reason = "klant niet actief"
        elif tenant_slug is not None and tenant.slug != tenant_slug:
            reason = f"verkeerd subdomein ({tenant_slug})"
        actor = (
            Actor("user", user.id, user.email, user.role) if user else Actor("user", None, email)
        )
        await audit.record(
            session,
            tenant_id=tenant.id if tenant else None,
            actor=actor,
            action="auth.login" if reason is None else "auth.login_failed",
            outcome="success" if reason is None else "denied",
            target_type="user",
            target_id=user.id if user else None,
            details={"reason": reason} if reason else {},
            info=info,
        )
        if reason is not None:
            return None
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        user.last_login_at = datetime.now(UTC)
        return user, tenant


def _principal(user: User, tenant: Tenant) -> Principal:
    return Principal(user_id=user.id, tenant_id=tenant.id, tenant_slug=tenant.slug, role=user.role)


async def start_session(db: Database, user: User, tenant: Tenant, days: int) -> LoginResult:
    token, token_hash = new_refresh_token()
    async with db.tenant_session(tenant.id) as session:
        session.add(
            RefreshToken(
                tenant_id=tenant.id,
                user_id=user.id,
                token_hash=token_hash,
                family_id=uuid.uuid4(),
                expires_at=datetime.now(UTC) + timedelta(days=days),
            )
        )
    return LoginResult(_principal(user, tenant), token, user, tenant)


async def rotate_session(
    db: Database, refresh_token: str, days: int, info: RequestInfo | None = None
) -> LoginResult | None:
    """Wissel een refresh-token in voor een nieuw token (rotatie).

    Wordt een al gebruikt token opnieuw aangeboden, dan is het waarschijnlijk gestolen:
    de hele sessie (familie) wordt dan ingetrokken en dit komt in het auditlog.
    """
    now = datetime.now(UTC)
    token_hash = hash_refresh_token(refresh_token)
    async with db.system_session() as session:
        stored = await session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        )
        if stored is None:
            return None
        if stored.revoked_at is not None:
            await session.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.family_id == stored.family_id, RefreshToken.revoked_at.is_(None)
                )
                .values(revoked_at=now)
            )
            owner = await session.get(User, stored.user_id)
            await audit.record(
                session,
                tenant_id=stored.tenant_id,
                actor=Actor("user", stored.user_id, owner.email if owner else None),
                action="auth.session_reuse_detected",
                outcome="denied",
                target_type="user",
                target_id=stored.user_id,
                details={"reason": "oud refresh-token opnieuw gebruikt; sessie ingetrokken"},
                info=info,
            )
            return None
        if stored.expires_at <= now:
            return None
        row = (
            await session.execute(
                select(User, Tenant)
                .join(Tenant, Tenant.id == User.tenant_id)
                .where(User.id == stored.user_id)
            )
        ).first()
        if row is None or not row[0].is_active or row[1].status != "active":
            stored.revoked_at = now
            return None
        user, tenant = row
        stored.revoked_at = now
        new_token, new_hash = new_refresh_token()
        session.add(
            RefreshToken(
                tenant_id=tenant.id,
                user_id=user.id,
                token_hash=new_hash,
                family_id=stored.family_id,
                expires_at=now + timedelta(days=days),
            )
        )
        return LoginResult(_principal(user, tenant), new_token, user, tenant)


async def end_session(db: Database, refresh_token: str, info: RequestInfo | None = None) -> None:
    async with db.system_session() as session:
        stored = await session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh_token))
        )
        if stored is not None:
            await session.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.family_id == stored.family_id, RefreshToken.revoked_at.is_(None)
                )
                .values(revoked_at=datetime.now(UTC))
            )
            user = await session.get(User, stored.user_id)
            await audit.record(
                session,
                tenant_id=stored.tenant_id,
                actor=Actor("user", stored.user_id, user.email if user else None),
                action="auth.logout",
                target_type="user",
                target_id=stored.user_id,
                info=info,
            )


async def _revoke_user_tokens(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
