# Apps ontwikkelen voor myWork-Hub

> **Levend document.** Verandert er iets aan de templates (`templates/`), de generator
> (`scripts/new_app.py`), de SDK of het app-contract? Werk dit document dan bij in
> dezelfde commit. De tests in `tests/templates/` bewaken dat templates, generator en
> bestaande apps bij elkaar blijven passen.

Een app is bij myWork-Hub een **losse service**: een eigen FastAPI-applicatie in een
eigen container, met een eigen database-schema. Apps praten alleen via API's en events
met de core en met elkaar, nooit via elkaars database.

## Inhoud

1. [Snel starten: een app maken](#1-snel-starten-een-app-maken)
2. [Wat de generator aanmaakt en aanpast](#2-wat-de-generator-aanmaakt-en-aanpast)
3. [Opbouw van een app](#3-opbouw-van-een-app)
4. [Manifest](#manifest)
5. [De API van een app](#5-de-api-van-een-app)
6. [Samenwerken met andere apps](#6-samenwerken-met-andere-apps)
7. [Frontend en theming](#7-frontend-en-theming)
8. [Testen](#8-testen)
9. [Draaien, bouwen en uitrollen](#9-draaien-bouwen-en-uitrollen)
10. [Checklist voor een nieuwe app](#10-checklist-voor-een-nieuwe-app)
11. [Een app verwijderen](#11-een-app-verwijderen)

## 1. Snel starten: een app maken

```bash
uv run python scripts/new_app.py --id agenda --name "Agenda" \
    --description "Agenda's en afspraken"
uv sync --all-packages
uv run pytest apps/agenda tests/
docker compose up -d --build app-agenda core
curl http://localhost:8080/api/apps/agenda/items
```

De app werkt direct: `/health`, `/manifest`, een voorbeeld-endpoint `/items` en
API-documentatie op `http://localhost:8080/api/apps/agenda/docs`. De core ziet de app
op `http://localhost:8080/api/core/apps`.

### Regels voor de app-id

- 3 tot 40 tekens: kleine letters, cijfers en koppeltekens, beginnend met een letter,
  niet eindigend op of met twee koppeltekens achter elkaar.
- Niet: `core`, `web`, `gateway`, `api`, `admin` (gereserveerd).
- De id is blijvend: hij zit in URL's, servicenamen, rechten en events.

De Python-module krijgt de id met `_` in plaats van `-` (`agenda-plus` → `agenda_plus`).

## 2. Wat de generator aanmaakt en aanpast

| Stap | Bestand | Wat |
| --- | --- | --- |
| 1 | `apps/<id>/` | Nieuwe app uit `templates/app/` |
| 2 | `pyproject.toml` | App toegevoegd aan de uv-workspace (`members`) |
| 3 | `docker-compose.yml` | Service `app-<id>` (uit `templates/deploy/compose-service.yaml`) en `HUB_APPS` van de core |
| 4 | `deploy/kubernetes/base/app-<id>.yaml` | Deployment, Service, HPA en PDB (uit `templates/deploy/kubernetes-app.yaml`) |
| 5 | `deploy/kubernetes/base/kustomization.yaml` | Nieuw bestand opgenomen |
| 6 | `deploy/kubernetes/base/config.yaml` | App toegevoegd aan `HUB_APPS` |
| 7 | `deploy/kubernetes/overlays/production/kustomization.yaml` | Image `ghcr.io/wizzard722/mywork-hub-app-<id>` |
| 8 | `uv.lock` | Bijgewerkt (`uv lock`; overslaan met `--no-lock`) |

Niet nodig: de gateway (routeert automatisch `/api/apps/<id>/` naar `app-<id>`) en de
image-workflow (`scripts/images.py` vindt apps zelf).

## 3. Opbouw van een app

```
apps/<id>/
├── manifest.yaml           Wie de app is, rechten en events
├── pyproject.toml          Pakket mywork-app-<id>
├── README.md               Korte beschrijving van de app
├── src/<module>/
│   ├── __init__.py
│   └── main.py             FastAPI-app (via mywork_sdk.create_service)
└── tests/
    └── test_app.py         Tests van de app
```

`main.py` maakt de app met de SDK:

```python
manifest = load_manifest(os.environ.get("APP_MANIFEST", DEFAULT_MANIFEST))
app = create_service(name=manifest.id, version=manifest.version, manifest=manifest)
```

De SDK zorgt voor `GET /health` en `GET /manifest`. Alles daarna is de eigen API.
Grotere apps splitsen de API op in routers (`api/items.py`, …) en voegen die toe met
`app.include_router(...)`.

## Manifest

```yaml
id: agenda                       # = map-naam en app-id
name: Agenda                     # weergavenaam in de hub
version: 0.1.0                   # semver; verhogen bij elke release
description: Agenda's en afspraken
permissions:                     # wat deze app nodig heeft
  - core:users.read
  - contacts:contacts.read
provides_permissions:            # wat deze app aanbiedt aan anderen
  - agenda:events.read
  - agenda:events.write
publishes:                       # events die deze app verstuurt
  - name: agenda.event_created
    description: Er is een afspraak aangemaakt.
subscribes:                      # events waarop deze app reageert
  - contacts.contact_deleted
```

| Veld | Regel |
| --- | --- |
| `id` | Zie regels voor de app-id; moet gelijk zijn aan de map-naam |
| `permissions` / `provides_permissions` | `<app-id>:<onderwerp>.<actie>`, bijv. `files:files.read` |
| `publishes[].name` | `<app-id>.<gebeurtenis>` in kleine letters, bijv. `files.file_uploaded` |
| `subscribes` | Namen van events van andere apps |

Het manifest wordt gevalideerd door `mywork_sdk.AppManifest`; onbekende velden of
verkeerde namen geven een fout bij het starten. De core leest het manifest via
`/manifest` en weigert een app waarvan de id niet klopt met de configuratie.

## 5. De API van een app

- Publiek pad: `/api/apps/<id>/...` (via de gateway). De service zelf ziet paden zonder
  dat voorvoegsel; `ROOT_PATH` zorgt dat de OpenAPI-documentatie klopt.
- JSON, met Pydantic-modellen voor invoer en uitvoer (`response_model`).
- Meervoudige zelfstandige naamwoorden voor resources: `/items`, `/items/{id}`.
- Versie in het manifest; breek de API niet zonder de versie te verhogen.
- Geen status in de container bewaren (geen lokale bestanden of sessies): de app moet
  met meerdere kopieën naast elkaar kunnen draaien (Kubernetes schaalt automatisch).
- **Inloggen en klant:** de web-schil stuurt het toegangstoken van de core mee
  (`Authorization: Bearer ...`). Het token bevat de gebruiker (`sub`), de klant
  (`tid`, `tslug`) en de rol (`role`) en is te controleren met de publieke sleutel op
  `/api/core/.well-known/jwks.json` (EdDSA, audience `mywork-hub`). Een app slaat
  klantdata altijd op met `tenant_id` en gebruikt Row-Level Security zoals de core
  (zie `docs/architecture.md`, sectie 5).
- Fase 3 voegt aan de SDK een kant-en-klare afhankelijkheid toe die het token
  controleert en de klantcontext zet, plus rechtencontrole op basis van `permissions`.

## 6. Samenwerken met andere apps

- **API-aanroepen:** via de gateway, `/api/apps/<andere-app>/...`. Vanaf fase 3 met een
  service-token van de core, alleen met de rechten uit het eigen manifest.
- **Events:** vanaf fase 4 via de SDK (Redis Streams). Een app mag alleen events
  versturen die in `publishes` staan.
- **Nooit** rechtstreeks in de database van een andere app.

## 7. Frontend en theming

Het thema komt altijd uit de core. Een app-frontend:

- laadt `/api/core/theme/theme.css` (zonder subdomein: `?tenant=<klant>` uit het token);
- gebruikt alleen de CSS-variabelen `--mw-*` (bijv. `var(--mw-color-primary)`,
  `var(--mw-radius)`, `var(--mw-font-family)`), nooit vaste kleuren;
- definieert eigen vangnetwaarden alleen met `:where(:root) { --mw-...: ... }`
  (specificiteit 0), zodat het thema van de klant altijd wint;
- werkt in licht en donker (de variabelen wisselen automatisch).

Hoe app-schermen in de web-schil worden ingeladen, volgt in fase 5.

## 8. Testen

| Wat | Waar | Draaien |
| --- | --- | --- |
| Tests van de app | `apps/<id>/tests/` | `uv run pytest apps/<id>` |
| Docker en Kubernetes consistent | `tests/deploy/` | `uv run pytest tests/deploy` |
| Templates en generator | `tests/templates/` | `uv run pytest tests/templates` |

Elke nieuwe functie in een app krijgt tests in dezelfde commit. Gebruik
`fastapi.testclient.TestClient` zoals in `templates/app/tests/test_app.py`.

## 9. Draaien, bouwen en uitrollen

```bash
# Lokaal zonder Docker (poort 8000)
MODULE=agenda.main uv run python -m mywork_sdk.serve

# In Docker Compose
docker compose up -d --build app-agenda

# Alleen het image bouwen
uv run python scripts/images.py build --only mywork-hub-app-agenda

# Kubernetes (na publiceren van de images)
kubectl apply -k deploy/kubernetes/overlays/production
```

Het image wordt gebouwd met `docker/python-service.Dockerfile` op een gehardend
Chainguard-image (zie [containers.md](containers.md)). De workflow `Images` bouwt, scant
en publiceert het automatisch.

## 10. Checklist voor een nieuwe app

- [ ] Gemaakt met `scripts/new_app.py` (niet met de hand gekopieerd)
- [ ] `manifest.yaml` ingevuld: omschrijving, rechten, events
- [ ] Voorbeeld-endpoint `/items` vervangen door de echte API
- [ ] Tests geschreven en groen: `uv run pytest`
- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `apps/<id>/README.md` beschrijft wat de app doet
- [ ] `docs/architecture.md` bijgewerkt (mappenstructuur en eventueel keuzes)

## 11. Een app verwijderen

Er is (nog) geen script voor. Verwijder met de hand:

1. `apps/<id>/` en de regel in `members` van `pyproject.toml`; daarna `uv lock`
2. service `app-<id>` en de `HUB_APPS`-regel in `docker-compose.yml`
3. `deploy/kubernetes/base/app-<id>.yaml`, de regel in `kustomization.yaml` en in
   `HUB_APPS` van `config.yaml`
4. de image-regel in `deploy/kubernetes/overlays/production/kustomization.yaml`

`uv run pytest tests/` laat zien of er iets is blijven staan.
