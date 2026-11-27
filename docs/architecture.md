# Architectuur van myWork-Hub

> **Levend document.** Bij elke wijziging aan de structuur, een service, een app, de
> deployment of de tests wordt dit bestand in dezelfde commit bijgewerkt.
> Laatst bijgewerkt: fase 2+ (Alpine-images, reverse proxy, firewall, auditlog,
> LLM-assistent, productie-compose).

Documentatie:

| Document | Over |
| --- | --- |
| `docs/architecture.md` | Dit document: keuzes, onderdelen, structuur, tests |
| [`docs/apps.md`](apps.md) | Apps ontwikkelen: template, generator, manifest, checklist |
| [`docs/containers.md`](containers.md) | Gehardende images (Alpine), bouwen, scannen, publiceren |
| [`docs/security.md`](security.md) | Reverse proxy, gateway, netwerken, firewall, auditlog, assistent |

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
| Containers | Alpine Linux met vaste versies, gehardend (geen shell/apk, niet-root) |
| Data | PostgreSQL en Redis zijn onderdeel van de core hub (Compose én Kubernetes) |
| Ingang | Reverse proxy (Caddy; in Kubernetes de Ingress-controller) vóór de gateway |
| Herleidbaarheid | Onveranderbaar auditlog met hash-keten per klant |
| AI | LLM-assistent die apps bedient met de rechten van de gebruiker, na bevestiging |

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
- **assistent**: LLM-assistent (Claude) die met de tools uit de app-manifesten handelingen
  uitvoert namens de gebruiker, met diens token en na bevestiging (zie `docs/security.md`).
- **proxy**: publieke reverse proxy (Caddy) met TLS en beveiligingsheaders.
- **PostgreSQL en Redis**: onderdeel van de core hub.

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

## 5. Klanten, accounts en inloggen

### Klanten (tenants)

- Elke klant heeft een **slug** die ook het subdomein is: `acme` → `acme.<HUB_BASE_DOMAIN>`
  (in ontwikkeling `https://acme.localhost`; browsers sturen `*.localhost` naar je eigen
  computer).
- **Welke klant?** Komt een aanvraag binnen op een subdomein, dan is dat de klant. Zonder
  subdomein (basisdomein, `localhost`, IP-adres) volgt de klant uit het **account**
  waarmee iemand inlogt.
- Een e-mailadres is uniek over de hele hub: één account hoort bij precies één klant.
- Gereserveerde subdomeinen (geen klant): `www`, `api`, `app`, `admin`, `auth`, `login`,
  `static`, `assets`, `mail`, `status`, `hub`.
- Klanten aanmaken: `python -m core.cli create-tenant` of, als `HUB_ALLOW_SIGNUP=true`,
  zelf via `POST /api/core/signup`.

### Inloggen

```
Browser                              Core
  │ POST /auth/login (e-mail, wachtwoord)
  │ ────────────────────────────────▶ Argon2id-controle, klant uit subdomein/account
  │ ◀──────────────────────────────── toegangstoken (JWT, 15 min) in JSON
  │                                   refresh-token in httpOnly-cookie (30 dagen)
  │ GET /api/... met Authorization: Bearer <toegangstoken>
  │ POST /auth/refresh (cookie + X-Hub-Request: 1)
  │ ◀──────────────────────────────── nieuw toegangstoken, nieuw refresh-token
```

| Onderdeel | Keuze |
| --- | --- |
| Wachtwoorden | Argon2id, minimaal 12 tekens; bij onbekend e-mailadres even lang rekenen (geen timing-lek) |
| Toegangstoken | JWT, EdDSA (Ed25519), 15 minuten, met `sub` (gebruiker), `tid`/`tslug` (klant), `role` |
| Publieke sleutel | `GET /api/core/.well-known/jwks.json` — apps controleren tokens hiermee (fase 3) |
| Refresh-token | Willekeurig, alleen de SHA-256-hash in de database; cookie `httpOnly`, `Secure`, `SameSite=Strict`, pad `/api/core/auth` |
| Rotatie | Elk gebruik geeft een nieuw refresh-token; hergebruik van een oud token trekt de hele sessie in (diefstaldetectie) |
| CSRF | Refresh en uitloggen vereisen de header `X-Hub-Request: 1` (naast `SameSite=Strict`) |
| Klantbinding | Een token van klant A wordt geweigerd op het subdomein van klant B |
| Intrekken | Wachtwoord wijzigen of account uitschakelen trekt alle sessies van die gebruiker in |

Het toegangstoken staat in de web-schil alleen in het geheugen (niet in
`localStorage`); na herladen haalt de schil een nieuw token op met de cookie.

### Rollen

| Rol | Mag |
| --- | --- |
| `owner` (eigenaar) | Alles, ook eigenaren toevoegen/wijzigen en de klantnaam aanpassen |
| `admin` (beheerder) | Gebruikers (geen eigenaren) en het thema beheren |
| `member` (gebruiker) | De hub en apps gebruiken, eigen naam en wachtwoord wijzigen |

Er blijft altijd minimaal één actieve eigenaar; niemand kan zijn eigen rol wijzigen,
zichzelf uitschakelen of verwijderen.

### Afscherming tussen klanten (Row-Level Security)

- Alle tabellen met klantdata hebben `tenant_id` en een RLS-policy, met
  `FORCE ROW LEVEL SECURITY` (geldt ook voor de eigenaar van de tabellen).
- Elke transactie van de core draait als de rol `mywork_rls` (geen superuser, geen
  eigenaar) en zet één context:
  - **klantcontext** (`app.tenant_id`): alleen rijen van die klant zichtbaar en
    schrijfbaar;
  - **systeemcontext** (`app.system = on`): klantoverstijgend, alleen voor inloggen,
    aanmelden, thema opzoeken en de CLI.
- Zonder context is niets zichtbaar. Een vergeten filter in de code lekt dus geen data.
- Tests in `services/core/tests/test_users_and_tenancy.py` controleren dit rechtstreeks
  in PostgreSQL.

### Database en migraties

- PostgreSQL via SQLAlchemy (async, asyncpg); schema in Alembic-migraties
  (`services/core/src/core/migrations/`).
- Bij het starten migreert de core automatisch (`HUB_AUTO_MIGRATE`), beveiligd met een
  advisory lock: met meerdere replica's migreert er één tegelijk.
- Zonder `HUB_DATABASE_URL` start de core zonder database: alleen standaardthema en
  app-status, inloggen geeft 503.

### Instellingen van de core

| Variabele | Standaard | Betekenis |
| --- | --- | --- |
| `HUB_DATABASE_URL` | leeg | `postgresql+asyncpg://gebruiker:wachtwoord@host:5432/db` |
| `HUB_BASE_DOMAIN` | `localhost` | Klanten op `<klant>.<basisdomein>` |
| `HUB_PUBLIC_URL` | `http://localhost:8080` | Publiek adres; ook `iss` in tokens |
| `HUB_JWT_PRIVATE_KEY` / `HUB_JWT_PRIVATE_KEY_FILE` | leeg | Ed25519-sleutel (PEM); **verplicht in productie** |
| `HUB_ACCESS_TOKEN_MINUTES` | `15` | Geldigheid toegangstoken |
| `HUB_REFRESH_TOKEN_DAYS` | `30` | Geldigheid refresh-sessie |
| `HUB_COOKIE_SECURE` | `true` | Alleen `false` voor `http://localhost` |
| `HUB_ALLOW_SIGNUP` | `false` | Zelf aanmelden van nieuwe klanten |
| `HUB_AUTO_MIGRATE` | `true` | Migraties bij opstarten |
| `HUB_ENVIRONMENT` | `development` | `production` maakt een JWT-sleutel verplicht |
| `HUB_APPS` | leeg | Bekende apps: `id=url,...` |

### Beheeropdrachten (CLI)

```bash
docker compose exec core python -m core.cli create-tenant --slug acme --name "Acme BV" \
    --owner-email eigenaar@acme.nl --owner-name "Jan de Vries"      # vraagt wachtwoord
docker compose exec core python -m core.cli migrate
docker compose run --rm --entrypoint python core -m core.cli generate-key
```

### API van de core (fase 2)

| Methode en pad | Wie | Doel |
| --- | --- | --- |
| `POST /auth/login`, `/auth/refresh`, `/auth/logout` | iedereen | Inloggen en sessies |
| `GET`/`PATCH /me`, `POST /me/password` | ingelogd | Eigen account |
| `PUT /me/preferences` | ingelogd | Voorkeuren (startbalk: positie, automatisch verbergen) |
| `GET /tenant/public` | iedereen | Klantnaam voor het inlogscherm |
| `GET /tenant`, `PATCH /tenant` | ingelogd / eigenaar | Eigen klant |
| `POST /signup` | iedereen (als aan) | Nieuwe klant met eigenaar |
| `GET`/`POST /users`, `PATCH`/`DELETE /users/{id}` | beheerder | Gebruikersbeheer |
| `GET /theme`, `GET /theme/theme.css` | iedereen | Thema (subdomein of `?tenant=`) |
| `PUT`/`DELETE /theme` | beheerder | Thema opslaan of terugzetten |
| `GET /.well-known/jwks.json` | iedereen | Publieke sleutel voor tokens |
| `GET /audit`, `GET /audit/verify`, `GET /audit/export.csv` | beheerder | Auditlog inzien, controleren, exporteren (zie `docs/security.md`) |
| `POST /audit/events` | ingelogd | Handeling van de assistent vastleggen |
| `GET /tls/ask` | proxy | Mag de proxy een certificaat aanvragen voor dit (sub)domein? |
| `GET /apps` | iedereen | Status van apps (fase 3: per klant en met inloggen) |

Volledige documentatie: `https://localhost/api/core/docs`.

## 6. Theming

De core is de enige bron van het thema, **per klant**:

- `GET /api/core/theme` — naam, logo, favicon en alle waarden als JSON.
- `GET /api/core/theme/theme.css` — dezelfde waarden als CSS-variabelen
  (`--mw-color-primary`, `--mw-font-family`, `--mw-radius`, …), met licht en donker.
- Welke klant: het subdomein, anders `?tenant=<klant>`, anders het standaardthema.
  Heeft een klant geen eigen thema, dan geldt het standaardthema met de klantnaam.
- `theme.css` wordt altijd hervalideerd (`Cache-Control: no-cache` met `ETag`): een
  opgeslagen thema is direct zichtbaar, een ongewijzigd thema kost alleen een 304.
- Beheerders wijzigen het thema in de web-schil (Beheer → Thema) of via `PUT /theme`.

De web-schil en alle app-frontends laden `theme.css` en gebruiken **alleen** de
`--mw-*`-variabelen, nooit vaste kleuren. Eigen vangnetwaarden definiëren frontends met
`:where(:root)` (specificiteit 0), zodat het thema van de core altijd wint. Kleuren worden
alleen als hex-waarde geaccepteerd; logo- en favicon-adressen alleen als `https://` of
pad op dezelfde site; lettertypen en maten worden gevalideerd. Klantinvoer kan zo geen
eigen CSS of scripts injecteren.

## 6a. Web-schil: bureaublad met windowmanager

De web-schil is een bureaublad zoals Windows (uitgewerkt vanuit ontwerp-variant B):

- **Vensters:** apps en onderdelen (Gebruikers, Thema, Auditlog, Assistent, elke app)
  openen in vensters die naast elkaar draaien: verplaatsen, schalen, minimaliseren,
  maximaliseren (ook dubbelklik op de titelbalk), sluiten.
- **Snap:** venster naar de linker- of rechterrand slepen = helft, naar een hoek = kwart,
  naar de bovenrand = volledig scherm; een voorbeeldvlak toont waar het venster komt.
  Via de knop **Indeling** in de titelbalk: twee naast elkaar, boven/onder, **vier
  kwarten**, één groot + twee klein, volledig. Toetsenbord: Ctrl+Alt+pijltjes.
  Losslepen zet het venster terug op de oude grootte.
- **Startbalk:** standaard onder, **automatisch verbergen** (op een randje van 4 px na);
  komt omhoog zodra de muis de rand nadert of erover beweegt, en bij toetsenbordfocus.
  Te verplaatsen naar **onder, boven, links of rechts** (Account-menu). Bevat: Start
  (menu met zoeken, apps en beheer), knoppen van open vensters (klik = naar voren /
  minimaliseren), assistent, klok en account (startbalk-instellingen, uitloggen).
- **Voorkeuren** (positie, automatisch verbergen) staan per gebruiker op de server
  (`PUT /api/core/me/preferences`) en gelden dus op elk apparaat; de vensterindeling
  wordt per gebruiker in de browser onthouden.
- **Bureaublad:** begroeting, zoekveld en app-tegels; een tegel opent de app in een venster.
- **Apps in vensters:** heeft een app in zijn manifest een `ui`-pad, dan laadt de hub
  dat scherm in het venster (iframe, zelfde domein) en geeft het toegangstoken door via
  `postMessage` (zie `docs/apps.md`). Anders toont het venster een beschrijving.
- **Telefoon** (smaller dan 720 px): vensters schermvullend, startbalk vast onder.
- Code: `web/src/wm/` (`geometry.ts` en `windows.ts` zijn pure logica met eigen tests).

| Vier kwarten | Slepen naar de rand (snap) | Startbalk links |
| --- | --- | --- |
| ![Vier kwarten](screenshots/vensters-vier-kwarten.png) | ![Snap](screenshots/vensters-snap-slepen.png) | ![Startbalk links](screenshots/startbalk-links.png) |

| Auditlog | Assistent (vraagt bevestiging) |
| --- | --- |
| ![Auditlog](screenshots/auditlog.png) | ![Assistent](screenshots/assistent.png) |

| Inloggen | Start | Start met eigen thema |
| --- | --- | --- |
| ![Inloggen](screenshots/inloggen.png) | ![Start](screenshots/start.png) | ![Eigen thema](screenshots/start-eigen-thema.png) |

| Gebruikers | Thema | Telefoon |
| --- | --- | --- |
| ![Gebruikers](screenshots/gebruikers.png) | ![Thema](screenshots/thema.png) | ![Telefoon](screenshots/telefoon.png) |

## 7. Draaien: Docker en Kubernetes

Beide gebruiken dezelfde images: `mywork-hub-gateway`, `mywork-hub-core`,
`mywork-hub-app-<id>` en `mywork-hub-web`. Alle images zijn **gehardend**: gebouwd op
Alpine Linux (vaste versies; geen shell en apk, niet-root uid 65532, read-only bestandssysteem). Details,
bouwen en publiceren: [containers.md](containers.md).

| | Docker Compose | Kubernetes |
| --- | --- | --- |
| Voor | Kleine installaties, ontwikkelen | Productie, schalen |
| Bestand | `docker-compose.yml` | `deploy/kubernetes/` (Kustomize) |
| Ingang | gateway op poort 8080 | Ingress → gateway |
| Schalen | 1 container per service | HPA per service (CPU 70%), min. 2 replica's |
| Beschikbaarheid | `restart: unless-stopped` | PodDisruptionBudget, rolling updates, spreiding over nodes |
| PostgreSQL / Redis | Services `postgres` en `redis` (netwerk `data`) | StatefulSets `postgres` en `redis` met persistent volume (`base/data.yaml`) |
| Publieke ingang | `proxy` (Caddy, TLS, headers) op 80/443 | Ingress-controller |
| Firewall | Gescheiden netwerken + host-firewall (nftables) | NetworkPolicies, standaard alles geweigerd |
| Instellingen | `.env` | ConfigMap `hub-config`, Secret `hub-secrets` (verplicht: `HUB_DATABASE_URL`, `HUB_JWT_PRIVATE_KEY`) |
| Subdomeinen | `https://<klant>.localhost` (via Caddy) | Ingress voor `hub.example.com` en `*.hub.example.com` (wildcard-certificaat nodig) |
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
| Unit — core | `services/core/tests/test_theming.py`, `test_registry.py`, `test_security_units.py` | Theming (ook CSS-injectie, ETag), app-register, subdomeinen, wachtwoorden, tokens | `uv run pytest` |
| Auditlog — core | `services/core/tests/test_audit.py` | Alle handelingen vastgelegd (ook geweigerd), IP/request-id, filters, export, onveranderbaar (ook voor superuser), manipulatie gedetecteerd | `uv run pytest` |
| Database — core | `services/core/tests/test_auth.py`, `test_users_and_tenancy.py` | Inloggen, sessies, rotatie, rollen, gebruikersbeheer, thema per klant, CLI, Row-Level Security in PostgreSQL (tijdelijke database; vereist PostgreSQL-programma's of `HUB_TEST_DATABASE_URL`) | `uv run pytest` |
| Unit — apps | `apps/<id>/tests/` | API en manifest van de app | `uv run pytest` |
| Deployment | `tests/deploy/` | Compose en Kubernetes gelijk, probes, limieten, non-root, HPA/PDB, naamgeving | `uv run pytest` |
| Integratie | `tests/integration/test_services.py` | Core en app als echte processen die via HTTP praten | `uv run pytest` |
| Integratie — gateway | `tests/integration/test_gateway.py` | Echte nginx-config van gateway en web: routering, SPA, headers (vereist `nginx` en `dnsmasq`) | `uv run pytest` |
| Templates | `tests/templates/` | Generator maakt werkende app; `hello` gelijk aan templates; image-lijst compleet | `uv run pytest` |
| Assistent | `services/assistant/tests/` | Tools binnen de rol, gebruikerstoken doorgegeven, bevestiging vóór wijzigen, weigeren, onbekende tool/ongeldige invoer niet uitgevoerd, privacy van conversaties, auditregels, stap-limiet, verzoek aan de Anthropic API (nagebootst) | `uv run pytest` |
| SDK — inloggen | `packages/sdk/tests/test_auth.py`, `test_tools.py` | Tokencontrole via JWKS (sleutel, verloop, audience, rol), rollen, tool-specificaties | `uv run pytest` |
| Productie-compose | `tests/templates/test_images.py` | `docker-compose.prod.yml` actueel, alle images, geen build, verplichte geheimen | `uv run pytest` |
| Windowmanager | `web/src/__tests__/wm.test.ts` | Snap-zones (helften, kwarten), randdetectie, startbalk aan vier zijden, vensters openen/focus/minimaliseren/snap/terugzetten | `cd web && npm test` |
| Frontend | `web/src/__tests__/` | Inloggen, sessie hervatten, uitloggen, dock en tegels, rollen, gebruikers- en themabeheer, CSS-volgorde | `cd web && npm test` |
| Kubernetes-schema | CI-job `kubernetes` | Kustomize renderen + kubeconform | alleen CI |
| Images | CI-job `docker` | uid 65532 en geen shell in elk image | alleen CI |
| Rooktest | CI-job `docker` | Hele stack via gateway (`docker compose up`), klant aanmaken via CLI, inloggen op subdomein | alleen CI |
| Kwetsbaarheden | Workflow `Images` | Trivy-scan van elk image (HIGH/CRITICAL) | alleen CI |

Regel: nieuwe code komt met tests in dezelfde commit.

## 9. Ontwerp (mockups)

**Gekozen: variant B** (gebouwd in fase 2, zie 6a). Beide varianten staan op een
ontwerpcanvas:
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
├── docker-compose.yml                 Hele hub op één machine, bouwt zelf (ontwikkeling/test)
├── docker-compose.prod.yml            Productie: alle images uit de registry (gegenereerd)
├── .env.example                       Voorbeeldinstellingen voor Docker
├── .dockerignore / .gitignore
├── .github/workflows/
│   ├── ci.yml                         Tests, Kubernetes-validatie, image-checks, rooktest
│   └── images.yml                     Images bouwen, scannen (Trivy), publiceren (GHCR)
├── branding/                          Logo's (SVG) en voorbeeld
├── docs/
│   ├── architecture.md                Dit document
│   ├── screenshots/                   Schermafbeeldingen van de web-schil
│   ├── apps.md                        Handleiding apps ontwikkelen
│   ├── security.md                    Proxy, gateway, netwerken, firewall, auditlog, assistent
│   └── containers.md                  Gehardende containers, bouwen en publiceren
├── scripts/
│   ├── new_app.py                     Nieuwe app maken uit de templates
│   ├── make_prod_compose.py           docker-compose.prod.yml genereren
│   └── images.py                      Alle images opsommen en bouwen
├── templates/
│   ├── app/                           Sjabloon voor apps/<id>/
│   └── deploy/                        Sjablonen voor Compose-service en Kubernetes
├── packages/
│   └── sdk/                           Python-SDK voor core en apps (mywork_sdk)
│       ├── src/mywork_sdk/
│       │   ├── manifest.py            AppManifest, EventSpec, load_manifest
│       │   ├── service.py             create_service: /health en /manifest
│       │   ├── auth.py                Tokens van de core controleren (JWKS), current_user
│       │   ├── testing.py             login_as/fake_user voor tests van apps
│       │   └── serve.py               Starter voor containers zonder shell
│       └── tests/
├── services/
│   └── core/                          Core-service
│       ├── src/core/
│       │   ├── main.py                App-fabriek: opstarten, database, migraties, sleutels
│       │   ├── config.py              Instellingen (HUB_*)
│       │   ├── db.py                  Database met klant- en systeemcontext (RLS)
│       │   ├── models.py              Tabellen: tenants, users, refresh_tokens, tenant_themes
│       │   ├── migrations/            Alembic-migraties (schema en RLS-policies)
│       │   ├── migrate.py             Migreren met advisory lock
│       │   ├── security.py            Argon2id, JWT (Ed25519), JWKS, refresh-tokens
│       │   ├── tenancy.py             Klant uit subdomein
│       │   ├── accounts.py            Klanten, gebruikers, sessies (servicelaag, met audit)
│       │   ├── audit.py               Auditlog: vastleggen, hash-keten, verificatie
│       │   ├── deps.py                FastAPI-afhankelijkheden (ingelogde gebruiker, rollen)
│       │   ├── routers/               API: auth, users, tenants, audit, schemas
│       │   ├── theming.py             Thema per klant als JSON en CSS
│       │   ├── registry.py            App-register en statuscontrole
│       │   └── cli.py                 Beheeropdrachten (create-tenant, migrate, generate-key)
│       └── tests/                     Unit- en databasetests (conftest start PostgreSQL)
│   └── assistant/                     LLM-assistent
│       ├── src/assistant/
│       │   ├── main.py                API: /status, /chat, /chat/{id}/decisions
│       │   ├── agent.py               Agent-lus, bevestiging, auditlog
│       │   ├── tools.py               Tools uit manifesten en core, uitvoeren met gebruikerstoken
│       │   ├── llm.py                 Koppeling met de Anthropic API (Claude)
│       │   ├── store.py               Conversaties in Redis
│       │   └── config.py              Instellingen
│       └── tests/                     Tests met nep-taalmodel en nagebootste apps
├── apps/
│   └── hello/                         Voorbeeld-app als losse service
│       ├── manifest.yaml
│       ├── src/hello/main.py
│       └── tests/
├── web/                               React-schil (Vite + TypeScript)
│   ├── index.html                     Laadt favicon en theme.css uit de core
│   ├── public/                        favicon.svg, logo-mark.svg
│   ├── src/
│   │   ├── main.tsx / App.tsx         Opstarten, routering, inloggen of hub
│   │   ├── api.ts                     Aanroepen naar de core (token in geheugen, refresh)
│   │   ├── auth/AuthProvider.tsx      Inlogstatus, sessie hervatten, uitloggen
│   │   ├── theme/ThemeProvider.tsx    Thema van de klant (naam, logo, favicon, theme.css)
│   │   ├── components/                AssistantPanel, Icon
│   │   ├── wm/                        Windowmanager: Desktop, WindowFrame, Taskbar, AppWindow,
│   │   │                              geometry.ts (snap-zones), windows.ts (venstertoestand)
│   │   ├── pages/                     Inloggen, Start, Gebruikers, Thema, Auditlog
│   │   ├── styles.css                 Alleen --mw-*-variabelen
│   │   └── __tests__/                 Frontend-tests (Vitest)
│   ├── nginx.conf / Dockerfile        nginx (Alpine), poort 8080, uid 65532
│   └── vite.config.ts / vitest.config.ts
├── proxy/
│   ├── Caddyfile                      Publieke reverse proxy: TLS, headers, limieten
│   └── Dockerfile                     Caddy (Alpine), gehardend
├── gateway/
│   ├── nginx.conf                     Routering, rate limiting, echte client-IP
│   ├── env.conf                       DNS-instellingen voor Docker (Kubernetes: ConfigMap)
│   └── Dockerfile                     nginx (Alpine), gehardend
├── docker/
│   ├── python-service.Dockerfile      Gedeelde Dockerfile voor core, assistent en apps (Python, Alpine)
│   └── empty/                         Lege map voor services zonder manifest
├── deploy/
│   └── kubernetes/
│       ├── base/                      Deployments, StatefulSets (PostgreSQL, Redis), Services,
│       │                              HPA, PDB, Ingress, ConfigMaps, NetworkPolicies
│       └── overlays/production/       Namespace, images, domeinnaam
│   └── firewall/nftables.conf         Host-firewall (alleen 80/443 en SSH)
└── tests/
    ├── deploy/                        Tests op Docker- en Kubernetes-configuratie
    ├── integration/                   Integratietests: services en gateway
    └── templates/                     Tests op templates, generator en image-lijst
```

## 12. Fasering

1. **Projectopzet** ✅ — monorepo, SDK, core, voorbeeld-app, gateway, web-schil, Docker,
   Kubernetes, tests, CI, mockups, app-template en generator, gehardende containers, logo.
2. **Klanten en accounts** ✅ — klanten (subdomein of account), eigen accounts,
   inloggen met sessies, rollen, gebruikersbeheer, Row-Level Security, thema per klant,
   web-schil variant B met inlogscherm en beheer.
3. App-register in de database, apps per klant aan/uit, service-tokens.
4. Events tussen apps via Redis Streams; twee voorbeeld-apps die data uitwisselen.
5. App-schermen in de web-schil inladen (de schil zelf, variant B, staat er sinds fase 2).
