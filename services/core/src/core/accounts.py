"""Klanten, gebruikers en inlogsessies (servicelaag, zonder HTTP)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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


# --- Klanten -------------------------------------------------------------------------


async def create_tenant(
    db: Database,
    *,
    slug: str,
    name: str,
    owner_email: str,
    owner_password: str,
    owner_name: str,
) -> tuple[Tenant, User]:
    slug = slug.strip().lower()
    if not valid_slug(slug):
        raise AccountError("Ongeldige klantnaam voor het subdomein")
    check_password(owner_password)
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
    return tenant, owner


async def get_tenant_by_slug(db: Database, slug: str) -> Tenant | None:
    async with db.system_session() as session:
        return await session.scalar(select(Tenant).where(Tenant.slug == slug))


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
    db: Database, actor: Principal, *, email: str, password: str, display_name: str, role: str
) -> User:
    if role == "owner" and actor.role != "owner":
        raise AccountError("Alleen een eigenaar kan een eigenaar toevoegen", 403)
    async with db.tenant_session(actor.tenant_id) as session:
        return await _insert_user(
            session,
            tenant_id=actor.tenant_id,
            email=email,
            password=password,
            display_name=display_name,
            role=role,
        )


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


async def update_user(
    db: Database,
    actor: Principal,
    user_id: uuid.UUID,
    *,
    display_name: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    password: str | None = None,
) -> User:
    async with db.tenant_session(actor.tenant_id) as session:
        user = await session.get(User, user_id, with_for_update=True)
        if user is None:
            raise AccountError("Gebruiker niet gevonden", 404)
        touches_owner = user.role == "owner" or role == "owner"
        if touches_owner and actor.role != "owner":
            raise AccountError("Alleen een eigenaar kan eigenaren wijzigen", 403)
        loses_owner = user.role == "owner" and (
            (role is not None and role != "owner") or is_active is False
        )
        if loses_owner and await _active_owner_count(session) <= 1:
            raise AccountError("Er moet minimaal één actieve eigenaar blijven", 409)
        if user.id == actor.user_id and (is_active is False or (role and role != user.role)):
            raise AccountError("Je kunt je eigen rol of account niet uitschakelen", 409)
        if display_name is not None:
            user.display_name = display_name.strip()
        if role is not None:
            user.role = role
        if is_active is not None:
            user.is_active = is_active
        if password is not None:
            check_password(password)
            user.password_hash = hash_password(password)
        if is_active is False or password is not None:
            await _revoke_user_tokens(session, user.id)
        await session.flush()
        await session.refresh(user)
        return user


async def delete_user(db: Database, actor: Principal, user_id: uuid.UUID) -> None:
    async with db.tenant_session(actor.tenant_id) as session:
        user = await session.get(User, user_id, with_for_update=True)
        if user is None:
            raise AccountError("Gebruiker niet gevonden", 404)
        if user.id == actor.user_id:
            raise AccountError("Je kunt je eigen account niet verwijderen", 409)
        if user.role == "owner":
            if actor.role != "owner":
                raise AccountError("Alleen een eigenaar kan eigenaren verwijderen", 403)
            if await _active_owner_count(session) <= 1:
                raise AccountError("Er moet minimaal één actieve eigenaar blijven", 409)
        await session.delete(user)


async def change_own_password(
    db: Database, principal: Principal, current_password: str, new_password: str
) -> None:
    async with db.tenant_session(principal.tenant_id) as session:
        user = await session.get(User, principal.user_id, with_for_update=True)
        if user is None or not verify_password(user.password_hash, current_password):
            raise AccountError("Huidig wachtwoord klopt niet", 400)
        check_password(new_password)
        user.password_hash = hash_password(new_password)
        await _revoke_user_tokens(session, user.id)


# --- Inloggen en sessies -------------------------------------------------------------


@dataclass
class LoginResult:
    principal: Principal
    refresh_token: str
    user: User
    tenant: Tenant


async def authenticate(
    db: Database, *, email: str, password: str, tenant_slug: str | None
) -> tuple[User, Tenant] | None:
    """Controleer e-mail en wachtwoord.

    De klant volgt uit het account. Komt de aanvraag binnen op een subdomein, dan moet
    het account bij die klant horen.
    """
    async with db.system_session() as session:
        row = (
            await session.execute(
                select(User, Tenant)
                .join(Tenant, Tenant.id == User.tenant_id)
                .where(User.email == normalize_email(email))
            )
        ).first()
        user, tenant = (row[0], row[1]) if row else (None, None)
        valid = verify_password(user.password_hash if user else None, password)
        if not valid or user is None or tenant is None:
            return None
        if not user.is_active or tenant.status != "active":
            return None
        if tenant_slug is not None and tenant.slug != tenant_slug:
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


async def rotate_session(db: Database, refresh_token: str, days: int) -> LoginResult | None:
    """Wissel een refresh-token in voor een nieuw token (rotatie).

    Wordt een al gebruikt token opnieuw aangeboden, dan is het waarschijnlijk gestolen:
    de hele sessie (familie) wordt dan ingetrokken.
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


async def end_session(db: Database, refresh_token: str) -> None:
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


async def _revoke_user_tokens(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
