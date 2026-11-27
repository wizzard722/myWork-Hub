import os
from pathlib import Path
from typing import Annotated

from fastapi import Path as PathParam
from pydantic import BaseModel

from mywork_sdk import create_service, load_manifest

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
