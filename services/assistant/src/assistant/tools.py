"""Tools van de assistent: opgebouwd uit de apps (manifest) en de core.

Rechten:
- Alleen tools waarvoor de rol van de gebruiker volstaat (``min_role``) worden aan het
  model aangeboden; andere tools bestaan voor het model niet.
- Elke aanroep gaat met het **token van de gebruiker** naar de app of de core. De app
  controleert zelf de rechten; de assistent heeft nooit meer rechten dan de gebruiker.
- Invoer wordt tegen het JSON-schema van de tool gecontroleerd vóór uitvoering.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
import jsonschema

from mywork_sdk import HubUser, ToolSpec
from mywork_sdk.auth import ROLE_ORDER

SEPARATOR = "__"
PARAM = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

# Ingebouwde tools van de core hub zelf.
CORE_TOOLS = [
    ToolSpec(
        name="whoami",
        description="Toon de gegevens van de ingelogde gebruiker (naam, e-mail, rol).",
        method="GET",
        path="/me",
    ),
    ToolSpec(
        name="list_apps",
        description="Toon welke apps in de hub zijn aangesloten en of ze bereikbaar zijn.",
        method="GET",
        path="/apps",
    ),
    ToolSpec(
        name="list_users",
        description=(
            "Toon alle gebruikers van de organisatie met rol en status (id nodig voor wijzigen)."
        ),
        method="GET",
        path="/users",
        min_role="admin",
    ),
    ToolSpec(
        name="change_user_role",
        description=(
            "Wijzig de rol van een gebruiker (member, admin of owner). "
            "Gebruik eerst list_users voor het id."
        ),
        method="PATCH",
        path="/users/{user_id}",
        min_role="admin",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "Id van de gebruiker"},
                "role": {"type": "string", "enum": ["member", "admin", "owner"]},
            },
            "required": ["user_id", "role"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="set_user_active",
        description=(
            "Schakel een gebruiker in (true) of uit (false). Gebruik eerst list_users voor het id."
        ),
        method="PATCH",
        path="/users/{user_id}",
        min_role="admin",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "Id van de gebruiker"},
                "is_active": {"type": "boolean"},
            },
            "required": ["user_id", "is_active"],
            "additionalProperties": False,
        },
    ),
]


@dataclass(frozen=True)
class Tool:
    app_id: str
    app_name: str
    base_url: str
    spec: ToolSpec

    @property
    def name(self) -> str:
        return f"{self.app_id}{SEPARATOR}{self.spec.name}"

    @property
    def needs_confirmation(self) -> bool:
        return self.spec.needs_confirmation

    def definition(self) -> dict[str, Any]:
        """Tooldefinitie voor het taalmodel."""
        note = " Vraagt de gebruiker eerst om bevestiging." if self.needs_confirmation else ""
        schema = dict(self.spec.input_schema or {"type": "object", "properties": {}})
        schema.setdefault("type", "object")
        return {
            "name": self.name,
            "description": f"[{self.app_name}] {self.spec.description}{note}",
            "input_schema": schema,
        }


@dataclass
class ToolResult:
    ok: bool
    status_code: int | None
    content: str


class Registry:
    """Haalt apps en hun tools op bij de core (met korte cache)."""

    def __init__(self, http: httpx.AsyncClient, core_url: str, cache_seconds: float = 30) -> None:
        self.http = http
        self.core_url = core_url.rstrip("/")
        self.cache_seconds = cache_seconds
        self._apps: list[dict] = []
        self._fetched = 0.0

    async def _app_list(self) -> list[dict]:
        if time.monotonic() - self._fetched > self.cache_seconds:
            try:
                response = await self.http.get(f"{self.core_url}/apps")
                response.raise_for_status()
                self._apps = response.json()
                self._fetched = time.monotonic()
            except httpx.HTTPError:
                pass  # vorige lijst blijven gebruiken
        return self._apps

    async def tools_for(self, user: HubUser) -> dict[str, Tool]:
        tools = [Tool("core", "Hub", self.core_url, spec) for spec in CORE_TOOLS]
        for app in await self._app_list():
            manifest = app.get("manifest") or {}
            if app.get("status") != "ok" or not manifest.get("tools"):
                continue
            for raw in manifest["tools"]:
                try:
                    spec = ToolSpec.model_validate(raw)
                except ValueError:
                    continue
                tools.append(Tool(app["id"], manifest.get("name", app["id"]), app["url"], spec))
        allowed = {
            t.name: t for t in tools if ROLE_ORDER.get(user.role, -1) >= ROLE_ORDER[t.spec.min_role]
        }
        return dict(sorted(allowed.items()))


def validate_input(tool: Tool, data: Any) -> str | None:
    """Foutmelding als de invoer niet aan het schema voldoet, anders None."""
    try:
        jsonschema.validate(data, tool.spec.input_schema or {"type": "object"})
    except jsonschema.ValidationError as exc:
        return f"Ongeldige invoer: {exc.message}"
    missing = [p for p in PARAM.findall(tool.spec.path) if p not in (data or {})]
    if missing:
        return f"Ongeldige invoer: ontbrekende waarde(n) {', '.join(missing)}"
    return None


async def execute(
    http: httpx.AsyncClient,
    tool: Tool,
    data: dict[str, Any],
    user: HubUser,
    *,
    request_id: str | None,
    timeout: float,
    max_chars: int,
) -> ToolResult:
    """Voer de tool uit bij de app, met het token van de gebruiker."""
    params = dict(data or {})
    path = PARAM.sub(lambda m: quote(str(params.pop(m.group(1))), safe=""), tool.spec.path)
    url = f"{tool.base_url.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {user.token}", "Accept": "application/json"}
    if request_id:
        headers["X-Request-ID"] = request_id
    method = tool.spec.method
    kwargs: dict[str, Any] = {"headers": headers, "timeout": timeout}
    if method in ("GET", "DELETE"):
        kwargs["params"] = {k: v for k, v in params.items() if v is not None}
    else:
        kwargs["json"] = params
    try:
        response = await http.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        return ToolResult(
            False, None, f"De app '{tool.app_id}' is niet bereikbaar ({type(exc).__name__})."
        )
    text = response.text
    try:
        text = json.dumps(response.json(), ensure_ascii=False)
    except ValueError:
        pass
    if len(text) > max_chars:
        text = text[:max_chars] + " …(ingekort)"
    if response.status_code >= 400:
        reason = {401: "niet ingelogd", 403: "geen rechten", 404: "niet gevonden"}.get(
            response.status_code, "fout"
        )
        return ToolResult(
            False, response.status_code, f"HTTP {response.status_code} ({reason}): {text}"
        )
    return ToolResult(True, response.status_code, text or "(geen inhoud)")
