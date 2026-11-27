"""Theming vanuit de core.

De core is de enige bron van het thema. De web-schil en alle app-frontends halen het
thema op bij de core en gebruiken uitsluitend de CSS-variabelen (``--mw-*``), zodat
een klant met één thema de hele hub van een eigen huisstijl voorziet.

Elke klant kan een eigen thema hebben (tabel ``tenant_themes``). Welk thema geldt:

1. de klant uit het subdomein (``acme.myworkhub.nl``), anders
2. ``?tenant=<klant>`` (voor de web-schil na inloggen zonder subdomein), anders
3. het standaardthema.

Heeft de klant geen eigen thema, dan geldt het standaardthema met de naam van de klant.
"""

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from core.deps import AdminDep, HostSlugDep
from core.models import Tenant, TenantTheme

# Alleen hex-kleuren: voorkomt dat klantinvoer willekeurige CSS in de stylesheet zet.
HEX_COLOR = r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"
# Lettertype-namen: letters, cijfers, spaties, komma's, koppeltekens en aanhalingstekens.
FONT_STACK = r"^[A-Za-z0-9 ,\-\"']{1,200}$"
CSS_LENGTH = r"^\d{1,3}(?:\.\d{1,2})?(?:px|rem)$"
# Logo en favicon: https-adres of pad op dezelfde site, zonder spaties of quotes.
ASSET_URL = r"^(?:https://[^\s\"'<>()]{1,500}|/[^\s\"'<>()]{0,500})$"


def _color(default: str) -> str:
    return Field(default=default, pattern=HEX_COLOR)


class ColorPalette(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str = _color("#0b5fff")
    primary_contrast: str = _color("#ffffff")
    background: str = _color("#f5f7fa")
    surface: str = _color("#ffffff")
    text: str = _color("#1b1f24")
    text_muted: str = _color("#5b6470")
    border: str = _color("#d9dee5")
    success: str = _color("#1a7f37")
    warning: str = _color("#9a6700")
    danger: str = _color("#cf222e")


DARK_DEFAULTS = ColorPalette(
    primary="#4c8dff",
    primary_contrast="#0b1220",
    background="#0f1318",
    surface="#171c23",
    text="#e6e9ee",
    text_muted="#9aa4b1",
    border="#2a313b",
    success="#3fb950",
    warning="#d29922",
    danger="#f85149",
)


class Theme(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="myWork-Hub", max_length=80)
    logo_url: str | None = Field(default=None, pattern=ASSET_URL)
    favicon_url: str | None = Field(default="/favicon.svg", pattern=ASSET_URL)
    font_family: str = Field(
        default='Inter, "Segoe UI", system-ui, -apple-system, sans-serif', pattern=FONT_STACK
    )
    radius: str = Field(default="8px", pattern=CSS_LENGTH)
    light: ColorPalette = Field(default_factory=ColorPalette)
    dark: ColorPalette = Field(default_factory=lambda: DARK_DEFAULTS.model_copy())


DEFAULT_THEME = Theme()


def _palette_vars(palette: ColorPalette) -> str:
    return "\n".join(
        f"  --mw-color-{key.replace('_', '-')}: {value};"
        for key, value in palette.model_dump().items()
    )


def render_css(theme: Theme) -> str:
    """Zet een thema om naar CSS-variabelen, met licht en donker."""
    return (
        ":root {\n"
        f"  --mw-font-family: {theme.font_family};\n"
        f"  --mw-radius: {theme.radius};\n"
        f"{_palette_vars(theme.light)}\n"
        "}\n"
        "@media (prefers-color-scheme: dark) {\n"
        ':root:not([data-theme="light"]) {\n'
        f"{_palette_vars(theme.dark)}\n"
        "}\n}\n"
        ':root[data-theme="dark"] {\n'
        f"{_palette_vars(theme.dark)}\n"
        "}\n"
    )


async def theme_for_slug(request, slug: str | None) -> Theme:
    """Thema van een klant, of het standaardthema."""
    db = getattr(request.app.state, "db", None)
    if db is None or not slug:
        return DEFAULT_THEME
    async with db.system_session() as session:
        row = (
            await session.execute(
                select(Tenant, TenantTheme)
                .outerjoin(TenantTheme, TenantTheme.tenant_id == Tenant.id)
                .where(Tenant.slug == slug, Tenant.status == "active")
            )
        ).first()
    if row is None:
        return DEFAULT_THEME
    tenant, stored = row
    if stored is None:
        return DEFAULT_THEME.model_copy(update={"name": tenant.name})
    return Theme.model_validate(stored.theme)


router = APIRouter(prefix="/theme", tags=["theming"])
TenantQuery = Query(default=None, max_length=40, description="Klant, als er geen subdomein is")


@router.get("", response_model=Theme)
async def read_theme(
    request: Request, host_slug: HostSlugDep, tenant: str | None = TenantQuery
) -> Theme:
    return await theme_for_slug(request, host_slug or tenant)


@router.get("/theme.css", response_class=Response)
async def read_theme_css(
    request: Request, host_slug: HostSlugDep, tenant: str | None = TenantQuery
) -> Response:
    theme = await theme_for_slug(request, host_slug or tenant)
    return Response(
        content=render_css(theme),
        media_type="text/css",
        headers={"Cache-Control": "public, max-age=300", "Vary": "Host"},
    )


@router.put("", response_model=Theme)
async def save_theme(theme: Theme, request: Request, principal: AdminDep) -> Theme:
    """Thema van de eigen klant opslaan (beheerders)."""
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Geen database geconfigureerd")
    async with db.tenant_session(principal.tenant_id) as session:
        stored = await session.get(TenantTheme, principal.tenant_id)
        if stored is None:
            session.add(TenantTheme(tenant_id=principal.tenant_id, theme=theme.model_dump()))
        else:
            stored.theme = theme.model_dump()
    return theme


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def reset_theme(request: Request, principal: AdminDep) -> Response:
    """Terug naar het standaardthema (beheerders)."""
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Geen database geconfigureerd")
    async with db.tenant_session(principal.tenant_id) as session:
        stored = await session.get(TenantTheme, principal.tenant_id)
        if stored is not None:
            await session.delete(stored)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
