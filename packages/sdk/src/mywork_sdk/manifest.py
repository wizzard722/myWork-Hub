"""Het app-manifest: hoe een app-service zichzelf bij de hub beschrijft."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

APP_ID_PATTERN = r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$"
EVENT_NAME_PATTERN = r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9_]*)+$"


class EventSpec(BaseModel):
    """Een event dat een app verstuurt, bijvoorbeeld ``files.file_uploaded``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=EVENT_NAME_PATTERN)
    description: str = ""


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


def load_manifest(path: str | Path) -> AppManifest:
    """Lees en valideer een ``manifest.yaml``."""
    with Path(path).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return AppManifest.model_validate(data)
