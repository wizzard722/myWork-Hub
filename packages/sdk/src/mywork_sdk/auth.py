"""Inloggen in apps: toegangstokens van de core controleren.

De core ondertekent toegangstokens met een Ed25519-sleutel; de publieke sleutel staat op
``<HUB_CORE_URL>/.well-known/jwks.json``. Deze module haalt die op (met cache), controleert
het token en geeft een ``HubUser`` met gebruiker, klant en rol.

Gebruik in een app::

    from mywork_sdk import HubUser, current_user, require_role

    @app.get("/items")
    def items(user: HubUser = Depends(current_user)): ...

    @app.delete("/items/{id}")
    def delete(id: int, user: HubUser = Depends(require_role("admin"))): ...

Sla klantdata altijd op met ``user.tenant_id``.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status

AUDIENCE = "mywork-hub"
ROLE_ORDER = {"member": 0, "admin": 1, "owner": 2}


@dataclass(frozen=True)
class HubUser:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_slug: str
    role: str
    token: str

    def has_role(self, minimum: str) -> bool:
        return ROLE_ORDER.get(self.role, -1) >= ROLE_ORDER[minimum]


class InvalidToken(Exception):
    pass


class HubAuth:
    """Controleert tokens met de publieke sleutel(s) van de core (JWKS)."""

    def __init__(
        self,
        core_url: str,
        *,
        issuer: str | None = None,
        cache_seconds: int = 300,
        http: httpx.Client | None = None,
    ) -> None:
        self.jwks_url = core_url.rstrip("/") + "/.well-known/jwks.json"
        self.issuer = issuer
        self.cache_seconds = cache_seconds
        self._http = http or httpx.Client(timeout=5)
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    def _refresh(self) -> None:
        response = self._http.get(self.jwks_url)
        response.raise_for_status()
        keys = {}
        for data in response.json().get("keys", []):
            key = jwt.PyJWK(data)
            keys[data.get("kid", "")] = key
        self._keys = keys
        self._fetched_at = time.monotonic()

    def _key(self, kid: str) -> jwt.PyJWK:
        with self._lock:
            stale = time.monotonic() - self._fetched_at > self.cache_seconds
            if stale or kid not in self._keys:
                try:
                    self._refresh()
                except httpx.HTTPError as exc:
                    if kid not in self._keys:
                        raise InvalidToken(f"sleutels niet op te halen: {exc}") from exc
            if kid not in self._keys:
                raise InvalidToken("onbekende sleutel")
            return self._keys[kid]

    def verify(self, token: str) -> HubUser:
        try:
            header = jwt.get_unverified_header(token)
            key = self._key(header.get("kid", ""))
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["EdDSA"],
                audience=AUDIENCE,
                issuer=self.issuer,
                options={
                    "require": ["exp", "sub", "tid", "role"],
                    "verify_iss": self.issuer is not None,
                },
            )
            if claims["role"] not in ROLE_ORDER:
                raise InvalidToken("onbekende rol")
            return HubUser(
                user_id=uuid.UUID(claims["sub"]),
                tenant_id=uuid.UUID(claims["tid"]),
                tenant_slug=claims.get("tslug", ""),
                role=claims["role"],
                token=token,
            )
        except (jwt.PyJWTError, ValueError, KeyError) as exc:
            raise InvalidToken(str(exc)) from exc


_default_auth: HubAuth | None = None


def get_auth() -> HubAuth:
    """De standaard-``HubAuth`` uit ``HUB_CORE_URL`` (en optioneel ``HUB_PUBLIC_URL``)."""
    global _default_auth
    if _default_auth is None:
        core_url = os.environ.get("HUB_CORE_URL", "http://core:8000")
        _default_auth = HubAuth(core_url, issuer=os.environ.get("HUB_TOKEN_ISSUER") or None)
    return _default_auth


def current_user(request: Request, auth: HubAuth = Depends(get_auth)) -> HubUser:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Niet ingelogd", headers={"WWW-Authenticate": "Bearer"}
        )
    try:
        return auth.verify(token)
    except InvalidToken:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Ongeldig of verlopen token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def require_role(minimum: str):
    """Afhankelijkheid: ingelogd met minimaal deze rol (member < admin < owner)."""
    if minimum not in ROLE_ORDER:
        raise ValueError(f"onbekende rol {minimum!r}")

    def dependency(user: HubUser = Depends(current_user)) -> HubUser:
        if not user.has_role(minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Minimaal rol '{minimum}' nodig")
        return user

    return dependency
