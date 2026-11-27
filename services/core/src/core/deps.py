"""Gedeelde FastAPI-afhankelijkheden: database, tokens, ingelogde gebruiker, klant."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import Settings, get_settings
from core.db import Database
from core.security import InvalidToken, Principal, TokenSigner
from core.tenancy import slug_from_host

_bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Database:
    db: Database | None = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Geen database geconfigureerd")
    return db


def get_signer(request: Request) -> TokenSigner:
    signer: TokenSigner | None = getattr(request.app.state, "signer", None)
    if signer is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Inloggen is niet beschikbaar")
    return signer


def host_tenant_slug(request: Request, settings: Settings = Depends(get_settings)) -> str | None:
    """Klant uit het subdomein van de aanvraag, of None."""
    return slug_from_host(request.headers.get("host"), settings.base_domain)


def current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    signer: TokenSigner = Depends(get_signer),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Niet ingelogd", headers={"WWW-Authenticate": "Bearer"}
        )
    try:
        principal = signer.verify(credentials.credentials)
    except InvalidToken:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Ongeldig of verlopen token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    # Een token van klant A is niet geldig op het subdomein van klant B.
    slug = slug_from_host(request.headers.get("host"), settings.base_domain)
    if slug is not None and slug != principal.tenant_slug:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token hoort bij een andere klant")
    return principal


def require_admin(principal: Principal = Depends(current_principal)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Alleen voor beheerders")
    return principal


DbDep = Annotated[Database, Depends(get_db)]
SignerDep = Annotated[TokenSigner, Depends(get_signer)]
PrincipalDep = Annotated[Principal, Depends(current_principal)]
AdminDep = Annotated[Principal, Depends(require_admin)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
HostSlugDep = Annotated[str | None, Depends(host_tenant_slug)]
