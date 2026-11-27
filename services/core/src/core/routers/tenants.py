"""Klantgegevens, aanmelden van nieuwe klanten en de publieke sleutel (JWKS)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import select

from core import accounts
from core.deps import DbDep, HostSlugDep, PrincipalDep, SettingsDep, SignerDep
from core.models import Tenant
from core.routers.auth import _session_response
from core.routers.schemas import SessionOut, SignupIn, TenantOut, TenantUpdate
from core.tenancy import slug_from_host

router = APIRouter(tags=["klanten"])


@router.get("/tenant/public", response_model=TenantOut)
async def public_tenant(
    db: DbDep, host_slug: HostSlugDep, tenant: str | None = Query(default=None, max_length=40)
) -> TenantOut:
    """Naam van de klant voor het inlogscherm (uit subdomein of ?tenant=)."""
    slug = host_slug or tenant
    found = await accounts.get_tenant_by_slug(db, slug) if slug else None
    if found is None or found.status != "active":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Onbekende klant")
    return TenantOut.model_validate(found)


@router.get("/tls/ask", include_in_schema=False)
async def tls_ask(
    request: Request,
    settings: SettingsDep,
    domain: str = Query(max_length=253),
) -> Response:
    """Voor de reverse proxy (Caddy on-demand TLS): mag voor dit domein een
    certificaat worden aangevraagd? Alleen het basisdomein en bestaande klanten."""
    domain = domain.strip().lower().rstrip(".")
    if domain == settings.base_domain.lower():
        return Response(status_code=status.HTTP_200_OK)
    slug = slug_from_host(domain, settings.base_domain)
    db = getattr(request.app.state, "db", None)
    if slug and db is not None:
        tenant = await accounts.get_tenant_by_slug(db, slug)
        if tenant is not None and tenant.status == "active":
            return Response(status_code=status.HTTP_200_OK)
    return Response(status_code=status.HTTP_404_NOT_FOUND)


@router.get("/tenant", response_model=TenantOut)
async def current_tenant(principal: PrincipalDep, db: DbDep) -> TenantOut:
    async with db.tenant_session(principal.tenant_id) as session:
        tenant = await session.scalar(select(Tenant))
    return TenantOut.model_validate(tenant)


@router.patch("/tenant", response_model=TenantOut)
async def update_tenant(body: TenantUpdate, principal: PrincipalDep, db: DbDep) -> TenantOut:
    if principal.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Alleen voor eigenaren")
    # Tenants zijn alleen in systeemcontext te wijzigen (RLS); beperk tot de eigen klant.
    async with db.system_session() as session:
        tenant = await session.get(Tenant, principal.tenant_id, with_for_update=True)
        tenant.name = body.name.strip()
    return TenantOut.model_validate(tenant)


@router.post("/signup", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def signup(
    body: SignupIn,
    request: Request,
    response: Response,
    db: DbDep,
    signer: SignerDep,
    settings: SettingsDep,
) -> SessionOut:
    if not settings.allow_signup:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Aanmelden is uitgeschakeld")
    tenant, owner = await accounts.create_tenant(
        db,
        slug=body.slug,
        name=body.tenant_name,
        owner_email=body.email,
        owner_password=body.password,
        owner_name=body.display_name,
    )
    result = await accounts.start_session(db, owner, tenant, settings.refresh_token_days)
    return _session_response(result, signer, response, request, settings)


@router.get("/.well-known/jwks.json", tags=["inloggen"])
def jwks(signer: SignerDep) -> dict:
    """Publieke sleutel waarmee apps toegangstokens controleren."""
    return signer.jwks()
