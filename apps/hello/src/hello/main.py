import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from fastapi import Path as PathParam
from pydantic import BaseModel

from mywork_sdk import HubUser, create_service, current_user, load_manifest

DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / "manifest.yaml"
manifest = load_manifest(os.environ.get("APP_MANIFEST", DEFAULT_MANIFEST))

app = create_service(
    name=manifest.id,
    version=manifest.version,
    manifest=manifest,
)


class Greeting(BaseModel):
    message: str


@app.get("/greetings/{name}", response_model=Greeting, tags=["greetings"])
def greet(name: Annotated[str, PathParam(min_length=1, max_length=100)]) -> Greeting:
    return Greeting(message=f"Hallo {name}, welkom bij myWork-Hub!")


class WhoAmI(BaseModel):
    user_id: str
    tenant: str
    role: str


@app.get("/whoami", response_model=WhoAmI, tags=["greetings"])
def whoami(user: HubUser = Depends(current_user)) -> WhoAmI:
    """Alleen voor ingelogde gebruikers: laat zien wat de app uit het token haalt."""
    return WhoAmI(user_id=str(user.user_id), tenant=user.tenant_slug, role=user.role)
