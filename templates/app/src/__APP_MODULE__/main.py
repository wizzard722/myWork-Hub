"""__APP_NAME__: app-service voor myWork-Hub.

De SDK levert /health en /manifest. Voeg hieronder de API van de app toe; andere apps
gebruiken alleen deze API (en events), nooit de database van deze app.
"""

import os
from pathlib import Path

from pydantic import BaseModel

from mywork_sdk import create_service, load_manifest

DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / "manifest.yaml"
manifest = load_manifest(os.environ.get("APP_MANIFEST", DEFAULT_MANIFEST))

app = create_service(name=manifest.id, version=manifest.version, manifest=manifest)


class Item(BaseModel):
    id: int
    title: str


# Voorbeeld-endpoint: vervang door de echte API van de app.
@app.get("/items", response_model=list[Item], tags=["items"])
def list_items() -> list[Item]:
    return [Item(id=1, title="Eerste item")]
