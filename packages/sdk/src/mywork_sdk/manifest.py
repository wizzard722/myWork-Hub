"""Het app-manifest: hoe een app-service zichzelf bij de hub beschrijft."""

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

APP_ID_PATTERN = r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$"
EVENT_NAME_PATTERN = r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9_]*)+$"


class EventSpec(BaseModel):
    """Een event dat een app verstuurt, bijvoorbeeld ``files.file_uploaded``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=EVENT_NAME_PATTERN)
    description: str = ""


TOOL_NAME_PATTERN = r"^[a-z][a-z0-9_]{1,40}$"


class ToolSpec(BaseModel):
    """Een handeling die de assistent namens de gebruiker mag uitvoeren.

    De assistent roept ``method path`` van de app aan met het token van de gebruiker;
    de app controleert zelf de rechten. Padparameters (``{name}``) komen uit de invoer;
    de rest gaat als query (GET/DELETE) of JSON-body (POST/PUT/PATCH).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=TOOL_NAME_PATTERN)
    description: str = Field(min_length=10, max_length=1000)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    path: str = Field(pattern=r"^/[A-Za-z0-9_\-/{}.]*$")
    input_schema: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    # Minimale rol om de tool aan te bieden (de app controleert daarnaast zelf).
    min_role: Literal["member", "admin", "owner"] = "member"
    # Vraag de gebruiker om bevestiging vóór uitvoeren. Standaard: alles behalve GET.
    confirm: bool | None = None

    @property
    def needs_confirmation(self) -> bool:
        return self.confirm if self.confirm is not None else self.method != "GET"


class AppManifest(BaseModel):
    """Beschrijving van een app-service.

    Een app levert dit manifest via ``GET /manifest``. De core gebruikt het om de app
    te registreren, rechten toe te kennen en events te routeren.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=APP_ID_PATTERN)
    name: str
    version: str
    description: str = ""
    # Rechten die de app nodig heeft, bijv. "core:users.read" of "files:read".
    permissions: list[str] = Field(default_factory=list)
    # Rechten die deze app zelf aanbiedt aan andere apps, bijv. "hello:greetings.read".
    provides_permissions: list[str] = Field(default_factory=list)
    publishes: list[EventSpec] = Field(default_factory=list)
    subscribes: list[str] = Field(default_factory=list)
    # Handelingen die de LLM-assistent namens de gebruiker mag uitvoeren.
    tools: list[ToolSpec] = Field(default_factory=list)
    # Pad van de eigen gebruikersinterface; de hub laadt die in een venster.
    ui: str | None = Field(default=None, pattern=r"^/[A-Za-z0-9_\-/.]*$")


def load_manifest(path: str | Path) -> AppManifest:
    """Lees en valideer een ``manifest.yaml``."""
    with Path(path).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return AppManifest.model_validate(data)
