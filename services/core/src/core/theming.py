"""Theming vanuit de core.

De core is de enige bron van het thema. De web-schil en alle app-frontends halen het
thema op bij de core en gebruiken uitsluitend de CSS-variabelen (``--mw-*``), zodat
een klant met één thema de hele hub van een eigen huisstijl voorziet.

Fase 1 levert het standaardthema. Vanaf fase 2 krijgt elke klant (tenant) een eigen
thema dat in de database wordt opgeslagen en hier wordt opgezocht.
"""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field

# Alleen hex-kleuren: voorkomt dat klantinvoer willekeurige CSS in de stylesheet zet.
HEX_COLOR = r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"
# Lettertype-namen: letters, cijfers, spaties, komma's, koppeltekens en aanhalingstekens.
FONT_STACK = r"^[A-Za-z0-9 ,\-\"']{1,200}$"
CSS_LENGTH = r"^\d{1,3}(?:\.\d{1,2})?(?:px|rem)$"


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
    logo_url: str | None = None
    favicon_url: str | None = None
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


def get_theme() -> Theme:
    # Fase 2: thema van de huidige klant opzoeken.
    return DEFAULT_THEME


router = APIRouter(prefix="/theme", tags=["theming"])


@router.get("", response_model=Theme)
def read_theme() -> Theme:
    return get_theme()


@router.get("/theme.css", response_class=Response)
def read_theme_css() -> Response:
    return Response(
        content=render_css(get_theme()),
        media_type="text/css",
        headers={"Cache-Control": "public, max-age=300"},
    )
