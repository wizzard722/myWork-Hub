# Architectuur van myWork-Hub

> **Levend document.** Bij elke wijziging aan de structuur, een service, een app, de
> deployment of de tests wordt dit bestand in dezelfde commit bijgewerkt.
> Laatst bijgewerkt: fase 1 (projectopzet, Kubernetes, tests, app-template,
> gehardende containers, logo).

Documentatie:

| Document | Over |
| --- | --- |
| `docs/architecture.md` | Dit document: keuzes, onderdelen, structuur, tests |
| [`docs/apps.md`](apps.md) | Apps ontwikkelen: template, generator, manifest, checklist |
| [`docs/containers.md`](containers.md) | Gehardende images, bouwen, scannen, publiceren |

myWork-Hub is een SaaS-platform in de geest van Nextcloud Hub: één hub waarin klanten
apps gebruiken (bestanden, agenda, taken, chat, …).

## 1. Uitgangspunten

| Keuze | Besluit |
| --- | --- |
| Doelgroep | SaaS voor klanten: meerdere klanten (tenants) op één installatie |
| Apps | **Losse services**, elk in een eigen container |
| Core | **Eén service** (modulair opgebouwd), niet opgeknipt in microservices |
| Gegevensuitwisseling | Uitsluitend via API's en events, nooit via elkaars database |
| Theming | Centraal vanuit de **core**, per klant |
| Techniek | Python 3.12 + FastAPI, React + TypeScript (Vite), PostgreSQL, Redis |
| Draaien | **Docker Compose** (kleine installaties) én **Kubernetes** (schalen) — dezelfde images |

### Waarom losse services voor apps, maar één core?

Volledig microservices ("alles los") is voor dit product te zwaar: veel bewegende delen,
lastig debuggen en duur voor kleine installaties. Eén monoliet past weer niet bij
apps die los ontwikkeld, uitgerold en geschaald moeten worden (ook door derden).

Daarom de tussenvorm:

- **Core = één service.** Klanten, gebruikers, rechten, app-register en theming horen
  bij elkaar en veranderen samen. Intern netjes in modules; opsplitsen kan later als
  één onderdeel echt apart moet schalen.
- **Elke app = eigen service.** Eigen release-ritme, eigen database-schema, apart te
  schalen (Bestanden heeft meer nodig dan Hello) en een fout in één app legt de rest
  niet plat.
- **Stateless services.** Geen sessies of bestanden lokaal in een container; status
  staat in PostgreSQL, Redis of objectopslag. Daardoor kan Kubernetes elke service
  vrij op- en afschalen.

Voor kleine installaties draait precies hetzelfde met Docker Compose op één machine.

## 2. Onderdelen

```
              Browser
                 │
          ┌──────▼──────┐   Docker: poort 8080
          │   gateway   │   Kubernetes: achter de Ingress
          └──┬───┬───┬──┘
   /api/core │   │   │ /api/apps/<id>         /
      ┌──────▼┐  │  ┌▼──────────┐       ┌────────┐
      │ core  │  │  │ app-<id>  │ …     │  web   │  React-schil
      └──┬──┬─┘  │  └──┬────────┘       └────────┘
         │  │    │     │
   ┌─────▼┐ └────┼─────▼──┐
   │ pg   │      │ redis  │  events (fase 4)
   └──────┘      └────────┘
```

- **gateway** (nginx): routeert `/api/core/*` naar de core, `/api/apps/<id>/*` naar de
  service `app-<id>` en de rest naar de web-schil. Een nieuwe app vraagt geen
  gateway-wijziging: de servicenaam volgt uit de app-id. `/healthz` voor probes.
- **core**: klanten, gebruikers, groepen, rollen, inloggen, app-register, theming,
  audit-log en meldingen.
- **app-services**: elk een eigen FastAPI-service, gebouwd op de gedeelde **SDK**
  (`packages/sdk`, Python-pakket `mywork_sdk`).
- **web**: de schil (inloggen, app-menu, thema) waarin de schermen van apps laden.

## 3. Het app-contract

Elke app-service levert minimaal:

| Endpoint | Doel |
| --- | --- |
| `GET /health` | Status voor core, Docker en Kubernetes-probes |
| `GET /manifest` | Wie de app is en wat hij nodig heeft / aanbiedt |
| `GET /openapi.json` | De API-beschrijving (automatisch door FastAPI) |

Het manifest (`manifest.yaml`, gevalideerd door `mywork_sdk.AppManifest`):

```yaml
id: hello                       # kleine letters, cijfers, koppeltekens
name: Hello
version: 0.1.0
permissions: []                 # rechten die de app gebruikt, bijv. core:users.read
provides_permissions:           # rechten die de app aan anderen aanbiedt
  - hello:greetings.read
publishes:                      # events die de app verstuurt
  - name: hello.greeted
subscribes: []                  # events waarop de app reageert
```

Naamgeving die overal gelijk moet zijn (bewaakt door tests):

| Wat | Waarde voor app `<id>` |
| --- | --- |
| Docker Compose-service / Kubernetes Deployment + Service | `app-<id>` |
| Publiek pad (gateway) | `/api/apps/<id>/` |
| `ROOT_PATH` van de service | `/api/apps/<id>` |
| Regel in `HUB_APPS` | `<id>=http://app-<id>:8000` |

## 4. Gegevensuitwisseling tussen apps

1. **Synchrone API-aanroepen**: app A roept de API van app B aan via
   `/api/apps/b/...`. Vanaf fase 3 haalt A daarvoor bij de core een kortlevend
   service-token op (OAuth2 client-credentials) voor één klant, met alleen de
   rechten uit zijn manifest. B controleert het token met de publieke sleutel van de
   core (JWKS) via de SDK.
2. **Events**: een app publiceert een event (bijv. `files.file_uploaded`) op Redis
   Streams. De core controleert of de app het event in zijn manifest heeft staan en
   levert het af bij apps die erop geabonneerd zijn en voor die klant aanstaan.

Elke aanvraag en elk event draagt de klant (tenant) mee; de SDK zet die context klaar.

## 5. Multi-tenancy

Eén PostgreSQL-cluster; elke service krijgt een eigen schema en database-gebruiker.
Elke tabel met klantdata heeft een `tenant_id` met PostgreSQL Row-Level Security, zodat
een fout in een app nooit data van een andere klant kan lekken. De klant wordt bepaald
uit het subdomein (`klant.myworkhub.nl`) en vastgelegd in het token.

## 6. Theming

De core is de enige bron van het thema:

- `GET /api/core/theme` — naam, logo, favicon en alle waarden als JSON.
- `GET /api/core/theme/theme.css` — dezelfde waarden als CSS-variabelen
  (`--mw-color-primary`, `--mw-font-family`, `--mw-radius`, …), met licht en donker.

De web-schil en alle app-frontends laden `theme.css` en gebruiken **alleen** de
`--mw-*`-variabelen, nooit vaste kleuren. Zo krijgt een klant met één thema de hele hub
in zijn huisstijl. Kleuren worden alleen als hex-waarde geaccepteerd en lettertypen en
maten worden gevalideerd, zodat klantinvoer geen eigen CSS kan injecteren.
Fase 1 levert het standaardthema; vanaf fase 2 heeft elke klant een eigen thema in de
database, te beheren via de core-API.

## 7. Draaien: Docker en Kubernetes

Beide gebruiken dezelfde images: `mywork-hub-gateway`, `mywork-hub-core`,
`mywork-hub-app-<id>` en `mywork-hub-web`. Alle images zijn **gehardend**: gebouwd op
Chainguard-images (geen shell, niet-root uid 65532, read-only bestandssysteem). Details,
bouwen en publiceren: [containers.md](containers.md).

| | Docker Compose | Kubernetes |
| --- | --- | --- |
| Voor | Kleine installaties, ontwikkelen | Productie, schalen |
| Bestand | `docker-compose.yml` | `deploy/kubernetes/` (Kustomize) |
| Ingang | gateway op poort 8080 | Ingress → gateway |
| Schalen | 1 container per service | HPA per service (CPU 70%), min. 2 replica's |
| Beschikbaarheid | `restart: unless-stopped` | PodDisruptionBudget, rolling updates, spreiding over nodes |
| PostgreSQL / Redis | Containers in de compose | Extern: managed dienst of operator (bijv. CloudNativePG) |
| Instellingen | `.env` | ConfigMap `hub-config`, Secret `hub-secrets` |
| DNS in gateway | `gateway/env.conf` (Docker-DNS, geen suffix) | ConfigMap `gateway-config` (kube-dns, suffix `.<namespace>.svc.cluster.local`) |

Starten:

```bash
docker compose up -d --build                                   # Docker
kubectl apply -k deploy/kubernetes/overlays/production         # Kubernetes
```

De productie-overlay zet namespace, image-namen/tags (`ghcr.io/wizzard722/...`) en de
domeinnaam. De workflow `Images` bouwt, scant en publiceert de images
(zie [containers.md](containers.md)).

## 8. Tests

Alle tests staan in de repository en draaien in CI (`.github/workflows/ci.yml`).

| Soort | Waar | Wat | Draaien |
| --- | --- | --- | --- |
| Unit — SDK | `packages/sdk/tests/` | Manifest-validatie, standaard-endpoints | `uv run pytest` |
| Unit — core | `services/core/tests/` | Theming (ook CSS-injectie), app-register, config | `uv run pytest` |
| Unit — apps | `apps/<id>/tests/` | API en manifest van de app | `uv run pytest` |
| Deployment | `tests/deploy/` | Compose en Kubernetes gelijk, probes, limieten, non-root, HPA/PDB, naamgeving | `uv run pytest` |
| Integratie | `tests/integration/test_services.py` | Core en app als echte processen die via HTTP praten | `uv run pytest` |
| Integratie — gateway | `tests/integration/test_gateway.py` | Echte nginx-config van gateway en web: routering, SPA, headers (vereist `nginx` en `dnsmasq`) | `uv run pytest` |
| Templates | `tests/templates/` | Generator maakt werkende app; `hello` gelijk aan templates; image-lijst compleet | `uv run pytest` |
| Frontend | `web/src/__tests__/` | Web-schil: thema, app-lijst, foutmeldingen | `cd web && npm test` |
| Kubernetes-schema | CI-job `kubernetes` | Kustomize renderen + kubeconform | alleen CI |
| Images | CI-job `docker` | uid 65532 en geen shell in elk image | alleen CI |
| Rooktest | CI-job `docker` | Hele stack via gateway (`docker compose up`) | alleen CI |
| Kwetsbaarheden | Workflow `Images` | Trivy-scan van elk image (HIGH/CRITICAL) | alleen CI |

Regel: nieuwe code komt met tests in dezelfde commit.

## 9. Ontwerp (mockups)

Twee varianten van de core hub staan op een ontwerpcanvas:
<https://claude.ai/artifact/WLLG5HGAevDZpNTHW5YfBG>

- **Variant A — Zijbalk**: vaste navigatie links (apps en beheer), zoekbalk bovenaan,
  dashboard met widgets (vandaag, recente bestanden, taken, meldingen, app-status).
- **Variant B — App-dock bovenin**: apps als dock in een gekleurde bovenbalk, centrale
  zoekbalk, app-tegels en een activiteitenstroom.

Beide gebruiken alleen de themakleuren; de accentkleur is op het canvas aan te passen
om theming per klant te laten zien.

## 10. Logo en huisstijl

Bestanden in `branding/`:

| Bestand | Gebruik |
| --- | --- |
| `logo.svg` | Logo met woordmerk, voor lichte achtergronden |
| `logo-dark.svg` | Logo met woordmerk, voor donkere achtergronden |
| `logo-mark.svg` | Alleen het beeldmerk (ook favicon, `web/public/favicon.svg`) |
| `preview.png` | Voorbeeld van alle varianten |

Het beeldmerk is een hub: een centraal knooppunt (de core) met vijf verbonden
knooppunten (de apps), in de primaire kleur `#0b5fff`. Het woordmerk gebruikt Inter
(vet). Klanten vervangen het logo via hun thema (`logo_url`, `favicon_url`).

## 11. Structuur van de repository

```
mywork-hub/
├── CLAUDE.md                          Werkafspraken voor ontwikkelen met Claude
├── README.md                          Snel starten
├── LICENSE
├── pyproject.toml                     uv-workspace, ruff- en pytest-instellingen
├── uv.lock                            Vastgezette Python-afhankelijkheden
├── docker-compose.yml                 Hele hub op één machine (gehardende images)
├── .env.example                       Voorbeeldinstellingen voor Docker
├── .dockerignore / .gitignore
├── .github/workflows/
│   ├── ci.yml                         Tests, Kubernetes-validatie, image-checks, rooktest
│   └── images.yml                     Images bouwen, scannen (Trivy), publiceren (GHCR)
├── branding/                          Logo's (SVG) en voorbeeld
├── docs/
│   ├── architecture.md                Dit document
│   ├── apps.md                        Handleiding apps ontwikkelen
│   └── containers.md                  Gehardende containers, bouwen en publiceren
├── scripts/
│   ├── new_app.py                     Nieuwe app maken uit de templates
│   └── images.py                      Alle images opsommen en bouwen
├── templates/
│   ├── app/                           Sjabloon voor apps/<id>/
│   └── deploy/                        Sjablonen voor Compose-service en Kubernetes
├── packages/
│   └── sdk/                           Python-SDK voor core en apps (mywork_sdk)
│       ├── src/mywork_sdk/
│       │   ├── manifest.py            AppManifest, EventSpec, load_manifest
│       │   ├── service.py             create_service: /health en /manifest
│       │   └── serve.py               Starter voor containers zonder shell
│       └── tests/
├── services/
│   └── core/                          Core-service
│       ├── src/core/
│       │   ├── main.py                FastAPI-app
│       │   ├── config.py              Instellingen (HUB_*)
│       │   ├── theming.py             Thema als JSON en CSS
│       │   └── registry.py            App-register en statuscontrole
│       └── tests/
├── apps/
│   └── hello/                         Voorbeeld-app als losse service
│       ├── manifest.yaml
│       ├── src/hello/main.py
│       └── tests/
├── web/                               React-schil (Vite + TypeScript)
│   ├── index.html                     Laadt favicon en theme.css uit de core
│   ├── public/                        favicon.svg, logo-mark.svg
│   ├── src/
│   │   ├── main.tsx / App.tsx         Schil en app-overzicht
│   │   ├── api.ts                     Aanroepen naar de core
│   │   ├── theme/ThemeProvider.tsx    Thema-context (naam, logo, favicon)
│   │   ├── styles.css                 Alleen --mw-*-variabelen
│   │   └── __tests__/                 Frontend-tests (Vitest)
│   ├── nginx.conf / Dockerfile        Chainguard nginx, poort 8080, uid 65532
│   └── vite.config.ts / vitest.config.ts
├── gateway/
│   ├── nginx.conf                     Routering (Docker en Kubernetes)
│   ├── env.conf                       DNS-instellingen voor Docker (Kubernetes: ConfigMap)
│   └── Dockerfile                     Chainguard nginx
├── docker/
│   ├── python-service.Dockerfile      Gedeelde Dockerfile voor core en apps (Chainguard python)
│   └── empty/                         Lege map voor services zonder manifest
├── deploy/
│   └── kubernetes/
│       ├── base/                      Deployments, Services, HPA, PDB, Ingress, ConfigMaps
│       └── overlays/production/       Namespace, images, domeinnaam
└── tests/
    ├── deploy/                        Tests op Docker- en Kubernetes-configuratie
    ├── integration/                   Integratietests: services en gateway
    └── templates/                     Tests op templates, generator en image-lijst
```

## 12. Fasering

1. **Projectopzet** ✅ — monorepo, SDK, core, voorbeeld-app, gateway, web-schil, Docker,
   Kubernetes, tests, CI, mockups, app-template en generator, gehardende containers, logo.
2. Klanten, gebruikers, inloggen, rechten, Row-Level Security, thema per klant.
3. App-register in de database, apps per klant aan/uit, service-tokens.
4. Events tussen apps via Redis Streams; twee voorbeeld-apps die data uitwisselen.
5. Web-schil volgens gekozen mockup: inloggen, app-menu, ingeladen app-schermen,
   thema-beheer.
