# Architectuur van myWork-Hub

myWork-Hub is een SaaS-platform in de geest van Nextcloud Hub: één hub waarin klanten
apps gebruiken (bestanden, agenda, taken, chat, …). Dit document legt de basiskeuzes vast.

## Uitgangspunten

| Keuze | Besluit |
| --- | --- |
| Doelgroep | SaaS voor klanten: meerdere klanten (tenants) op één installatie |
| Apps | **Losse services**, elk in een eigen container |
| Gegevensuitwisseling | Uitsluitend via API's en events, nooit via elkaars database |
| Theming | Centraal vanuit de **core**, per klant |
| Techniek | Python 3.12 + FastAPI, React + TypeScript (Vite), PostgreSQL, Redis |
| Draaien | Docker Compose |

## Onderdelen

```
              Browser
                 │
          ┌──────▼──────┐
          │   gateway   │  nginx: enige publieke ingang (:8080)
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

- **gateway**: routeert `/api/core/*` naar de core, `/api/apps/<id>/*` naar de service
  `app-<id>` en de rest naar de web-schil. Een nieuwe app vraagt geen gateway-wijziging:
  de service-naam volgt uit de app-id.
- **core**: klanten, gebruikers, groepen, rollen, inloggen, app-register, theming,
  audit-log en meldingen.
- **app-services**: elk een eigen FastAPI-service met eigen database-schema. Bouwen op de
  gedeelde **SDK** (`packages/sdk`, Python-pakket `mywork_sdk`).
- **web**: de schil (inloggen, app-menu, thema) waarin de schermen van apps laden.

## Het app-contract

Elke app-service levert minimaal:

| Endpoint | Doel |
| --- | --- |
| `GET /health` | Status voor de core en Docker |
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

## Gegevensuitwisseling tussen apps

1. **Synchrone API-aanroepen**: app A roept de API van app B aan via
   `/api/apps/b/...`. Vanaf fase 3 haalt A daarvoor bij de core een kortlevend
   service-token op (OAuth2 client-credentials) voor één klant, met alleen de
   rechten uit zijn manifest. B controleert het token met de publieke sleutel van de
   core (JWKS) via de SDK.
2. **Events**: een app publiceert een event (bijv. `files.file_uploaded`) op Redis
   Streams. De core controleert of de app het event in zijn manifest heeft staan en
   levert het af bij apps die erop geabonneerd zijn en voor die klant aanstaan.

Elke aanvraag en elk event draagt de klant (tenant) mee; de SDK zet die context klaar.

## Multi-tenancy

Eén PostgreSQL-cluster; elke service krijgt een eigen schema en database-gebruiker.
Elke tabel met klantdata heeft een `tenant_id` met PostgreSQL Row-Level Security, zodat
een fout in een app nooit data van een andere klant kan lekken. De klant wordt bepaald
uit het subdomein (`klant.myworkhub.nl`) en vastgelegd in het token.

## Theming

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

## Fasering

1. **Projectopzet** — monorepo, SDK, core, voorbeeld-app, gateway, web-schil, Docker, CI.
2. Klanten, gebruikers, inloggen, rechten, Row-Level Security, thema per klant.
3. App-register in de database, apps per klant aan/uit, service-tokens.
4. Events tussen apps via Redis Streams; twee voorbeeld-apps die data uitwisselen.
5. Web-schil: inloggen, app-menu, ingeladen app-schermen, thema-beheer.
