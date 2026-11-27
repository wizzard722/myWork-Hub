"""Inloggen, sessies vernieuwen, uitloggen en het eigen account."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from core import accounts
from core.accounts import LoginResult
from core.audit import RequestInfo
from core.deps import DbDep, HostSlugDep, PrincipalDep, SettingsDep, SignerDep
from core.routers.schemas import (
    LoginIn,
    MeUpdate,
    PasswordChange,
    Preferences,
    SessionOut,
    TenantOut,
    UserOut,
)
from core.security import TokenSigner

router = APIRouter(tags=["inloggen"])

REFRESH_COOKIE = "mw_refresh"
CSRF_HEADER = "X-Hub-Request"


def _cookie_path(request: Request) -> str:
    return request.scope.get("root_path", "").rstrip("/") + "/auth"


def _require_csrf_header(value: str | None) -> None:
    # Een eigen header kan een andere website niet zonder CORS-toestemming meesturen.
    if value != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Header {CSRF_HEADER}: 1 ontbreekt")


def _session_response(
    result: LoginResult,
    signer: TokenSigner,
    response: Response,
    request: Request,
    settings,
) -> SessionOut:
    response.set_cookie(
        REFRESH_COOKIE,
        result.refresh_token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=_cookie_path(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return SessionOut(
        access_token=signer.issue(result.principal),
        expires_in=int(signer.ttl.total_seconds()),
        user=UserOut.model_validate(result.user),
        tenant=TenantOut.model_validate(result.tenant),
    )


@router.post("/auth/login", response_model=SessionOut)
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: DbDep,
    signer: SignerDep,
    settings: SettingsDep,
    host_slug: HostSlugDep,
) -> SessionOut:
    slug = host_slug or (body.tenant.strip().lower() if body.tenant else None)
    found = await accounts.authenticate(
        db,
        email=body.email,
        password=body.password,
        tenant_slug=slug,
        info=RequestInfo.from_request(request),
    )
    if found is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mailadres of wachtwoord klopt niet")
    user, tenant = found
    result = await accounts.start_session(db, user, tenant, settings.refresh_token_days)
    return _session_response(result, signer, response, request, settings)


@router.post("/auth/refresh", response_model=SessionOut)
async def refresh(
    request: Request,
    response: Response,
    db: DbDep,
    signer: SignerDep,
    settings: SettingsDep,
    host_slug: HostSlugDep,
    mw_refresh: str | None = Cookie(default=None),
    x_hub_request: str | None = Header(default=None),
) -> SessionOut:
    _require_csrf_header(x_hub_request)
    result = None
    if mw_refresh:
        result = await accounts.rotate_session(
            db, mw_refresh, settings.refresh_token_days, RequestInfo.from_request(request)
        )
    if result is None or (host_slug is not None and result.tenant.slug != host_slug):
        expired = JSONResponse({"detail": "Sessie verlopen"}, status.HTTP_401_UNAUTHORIZED)
        expired.delete_cookie(REFRESH_COOKIE, path=_cookie_path(request))
        return expired
    return _session_response(result, signer, response, request, settings)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    db: DbDep,
    mw_refresh: str | None = Cookie(default=None),
    x_hub_request: str | None = Header(default=None),
) -> Response:
    _require_csrf_header(x_hub_request)
    if mw_refresh:
        await accounts.end_session(db, mw_refresh, RequestInfo.from_request(request))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_COOKIE, path=_cookie_path(request))
    return response


@router.get("/me", response_model=UserOut)
async def me(principal: PrincipalDep, db: DbDep) -> UserOut:
    user = await accounts.get_user(db, principal.tenant_id, principal.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account bestaat niet meer")
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: MeUpdate, request: Request, principal: PrincipalDep, db: DbDep
) -> UserOut:
    user = await accounts.update_user(
        db,
        principal,
        principal.user_id,
        display_name=body.display_name,
        info=RequestInfo.from_request(request),
    )
    return UserOut.model_validate(user)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChange, request: Request, principal: PrincipalDep, db: DbDep
) -> Response:
    await accounts.change_own_password(
        db, principal, body.current_password, body.new_password, RequestInfo.from_request(request)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/me/preferences", response_model=Preferences)
async def save_preferences(body: Preferences, principal: PrincipalDep, db: DbDep) -> Preferences:
    """Eigen voorkeuren opslaan (geen beheerhandeling, dus niet in het auditlog)."""
    from core.models import User

    async with db.tenant_session(principal.tenant_id) as session:
        user = await session.get(User, principal.user_id, with_for_update=True)
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account bestaat niet meer")
        user.preferences = body.model_dump()
    return body
