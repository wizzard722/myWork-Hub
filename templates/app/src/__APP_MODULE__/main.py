"""__APP_NAME__: app-service voor myWork-Hub.

De SDK levert /health en /manifest. Voeg hieronder de API van de app toe; andere apps
gebruiken alleen deze API (en events), nooit de database van deze app.

Inloggen: ``current_user`` controleert het token van de core en geeft gebruiker, klant
(``tenant_id``) en rol. Sla klantdata altijd op met ``user.tenant_id``.
"""

import os
from pathlib import Path

from fastapi import Depends
from pydantic import BaseModel

from mywork_sdk import HubUser, create_service, current_user, load_manifest, require_role

DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / "manifest.yaml"
manifest = load_manifest(os.environ.get("APP_MANIFEST", DEFAULT_MANIFEST))

app = create_service(name=manifest.id, version=manifest.version, manifest=manifest)


class Item(BaseModel):
    id: int
    title: str


class ItemIn(BaseModel):
    title: str


# Voorbeeld-endpoints: vervang door de echte API van de app.
@app.get("/items", response_model=list[Item], tags=["items"])
def list_items(user: HubUser = Depends(current_user)) -> list[Item]:
    return [Item(id=1, title=f"Eerste item van {user.tenant_slug}")]


@app.post("/items", response_model=Item, status_code=201, tags=["items"])
def add_item(body: ItemIn, user: HubUser = Depends(require_role("admin"))) -> Item:
    return Item(id=2, title=body.title)
