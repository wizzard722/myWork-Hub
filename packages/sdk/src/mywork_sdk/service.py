"""Fabriek voor FastAPI-services met de standaard-endpoints van de hub."""

from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel

from mywork_sdk.manifest import AppManifest


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded", "down"] = "ok"
    service: str
    version: str


def create_service(
    *,
    name: str,
    version: str,
    manifest: AppManifest | None = None,
    lifespan: Any = None,
) -> FastAPI:
    """Maak een service met ``GET /health`` en, voor apps, ``GET /manifest``.

    Het pad waarop de gateway de service publiceert (bijv. ``/api/apps/hello``)
    geeft de server mee via ``uvicorn --root-path`` (env ``ROOT_PATH``), zodat de
    OpenAPI-documentatie achter de gateway klopt.
    """
    app = FastAPI(title=name, version=version, lifespan=lifespan)

    @app.get("/health", response_model=HealthStatus, tags=["hub"])
    def health() -> HealthStatus:
        return HealthStatus(service=name, version=version)

    if manifest is not None:

        @app.get("/manifest", response_model=AppManifest, tags=["hub"])
        def get_manifest() -> AppManifest:
            return manifest

    return app
