"""App-register (fase 1): welke app-services zijn bekend en zijn ze bereikbaar?

Fase 3 vervangt de vaste lijst uit ``HUB_APPS`` door registratie in de database,
per klant aan of uit te zetten.
"""

import asyncio
from typing import Literal

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ValidationError

from core.config import Settings, get_settings
from mywork_sdk import AppManifest


class AppStatus(BaseModel):
    id: str
    url: str
    status: Literal["ok", "unreachable", "invalid"]
    manifest: AppManifest | None = None
    error: str | None = None


async def probe_app(client: httpx.AsyncClient, app_id: str, url: str) -> AppStatus:
    try:
        health = await client.get(f"{url}/health")
        health.raise_for_status()
        response = await client.get(f"{url}/manifest")
        response.raise_for_status()
        manifest = AppManifest.model_validate(response.json())
    except httpx.HTTPError as exc:
        return AppStatus(id=app_id, url=url, status="unreachable", error=type(exc).__name__)
    except (ValidationError, ValueError) as exc:
        return AppStatus(id=app_id, url=url, status="invalid", error=str(exc)[:500])
    if manifest.id != app_id:
        return AppStatus(
            id=app_id,
            url=url,
            status="invalid",
            error=f"manifest-id {manifest.id!r} wijkt af van geconfigureerde id",
        )
    return AppStatus(id=app_id, url=url, status="ok", manifest=manifest)


router = APIRouter(prefix="/apps", tags=["apps"])


@router.get("", response_model=list[AppStatus])
async def list_apps(settings: Settings = Depends(get_settings)) -> list[AppStatus]:
    apps = settings.app_urls()
    async with httpx.AsyncClient(timeout=settings.app_timeout_seconds) as client:
        return list(
            await asyncio.gather(*(probe_app(client, app_id, url) for app_id, url in apps.items()))
        )
