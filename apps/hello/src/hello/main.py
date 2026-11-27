import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from fastapi import Path as PathParam
from fastapi.responses import HTMLResponse, Response
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


# --- Eigen scherm (in een venster van de hub) ------------------------------------------
# Geen inline script: de Content-Security-Policy van de hub staat alleen eigen bestanden toe.

UI_HTML = """<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hello</title>
<link rel="stylesheet" href="/api/core/theme/theme.css">
<link rel="stylesheet" href="ui/style.css">
</head>
<body>
<main>
  <h1>Hallo!</h1>
  <p id="who" class="muted">Even kijken wie je bent…</p>
  <form id="greet">
    <label for="name">Wie wil je begroeten?</label>
    <div class="row"><input id="name" required maxlength="100"><button>Begroet</button></div>
  </form>
  <p id="answer" role="status"></p>
</main>
<script src="ui/app.js"></script>
</body>
</html>
"""

UI_CSS = """
body { margin: 0; font-family: var(--mw-font-family, system-ui);
  background: var(--mw-color-surface, #fff); color: var(--mw-color-text, #1b1f24); }
main { padding: 20px; max-width: 520px; }
h1 { margin: 0 0 8px; }
.muted { color: var(--mw-color-text-muted, #5b6470); }
label { display: block; font-weight: 600; margin: 16px 0 6px; }
.row { display: flex; gap: 8px; }
input { flex: 1; min-height: 40px; padding: 0 12px; font: inherit;
  border: 1px solid var(--mw-color-border, #d9dee5); border-radius: var(--mw-radius, 8px); }
button { min-height: 40px; padding: 0 16px; border: 0; cursor: pointer; font: inherit;
  border-radius: var(--mw-radius, 8px); background: var(--mw-color-primary, #0b5fff);
  color: var(--mw-color-primary-contrast, #fff); }
#answer { font-size: 1.2rem; margin-top: 16px; }
"""

UI_JS = """// Het token komt van de hub (zelfde domein) via postMessage.
let token = null;
window.addEventListener("message", async (event) => {
  if (event.origin !== window.location.origin || event.data?.type !== "mywork:token") return;
  token = event.data.token;
  const who = document.getElementById("who");
  const response = await fetch("whoami", { headers: { Authorization: `Bearer ${token}` } });
  if (response.ok) {
    const me = await response.json();
    who.textContent = `Ingelogd bij ${me.tenant} als ${me.role}.`;
  } else {
    who.textContent = "Niet ingelogd.";
  }
});
document.getElementById("greet").addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = document.getElementById("name").value.trim();
  const response = await fetch(`greetings/${encodeURIComponent(name)}`);
  const answer = document.getElementById("answer");
  answer.textContent = response.ok ? (await response.json()).message : "Dat lukte niet.";
});
"""


@app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def ui() -> HTMLResponse:
    return HTMLResponse(UI_HTML)


@app.get("/ui/style.css", include_in_schema=False)
def ui_css() -> Response:
    return Response(UI_CSS, media_type="text/css")


@app.get("/ui/app.js", include_in_schema=False)
def ui_js() -> Response:
    return Response(UI_JS, media_type="text/javascript")
