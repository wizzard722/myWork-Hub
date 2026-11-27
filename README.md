<p><img src="branding/logo.svg" alt="myWork-Hub" height="64"></p>

# myWork-Hub

Een SaaS-hub voor klanten, in de geest van Nextcloud Hub. Apps draaien als losse services
en wisselen gegevens uit via API's en events; de core regelt klanten, gebruikers, het
app-register en het thema.

Documentatie:

- [docs/architecture.md](docs/architecture.md) — architectuur, volledige mappenstructuur, tests, fasering
- [docs/apps.md](docs/apps.md) — apps ontwikkelen met de template en generator
- [docs/containers.md](docs/containers.md) — gehardende containers (Alpine), bouwen, productie-compose
- [docs/security.md](docs/security.md) — reverse proxy, firewall, auditlog, LLM-assistent

## Structuur (kort)

```
packages/sdk/       Python-SDK (mywork_sdk) voor core en apps
services/core/      Core-service: theming, app-register (later: klanten, gebruikers, auth)
apps/hello/         Voorbeeld-app als losse service
web/                React-schil (Vite + TypeScript)
gateway/            nginx: enige publieke ingang
deploy/kubernetes/  Kustomize voor Kubernetes
templates/          Sjablonen voor nieuwe apps
scripts/            new_app.py (app maken), images.py (images bouwen)
branding/           Logo's
tests/              Deployment-, integratie- en templatetests
```

## Starten met Docker

```bash
cp .env.example .env
docker compose up -d --build
# Eerste klant met eigenaar (vraagt om een wachtwoord van minimaal 12 tekens)
docker compose exec core python -m core.cli create-tenant --slug acme --name "Acme BV" \
    --owner-email eigenaar@acme.nl --owner-name "Jan de Vries"
```

Daarna (HTTPS met een eigen certificaat van Caddy; de browser waarschuwt eenmalig):

- https://acme.localhost — inloggen bij klant Acme (subdomein)
- https://localhost — inloggen zonder subdomein (klant volgt uit het account)
- https://localhost/api/core/docs — API-documentatie van de core

LLM-assistent aanzetten: zet `ANTHROPIC_API_KEY` in `.env`.

**Productie** met kant-en-klare images: `docker-compose.prod.yml` (zie
[docs/containers.md](docs/containers.md)).

## Draaien op Kubernetes

```bash
kubectl apply -k deploy/kubernetes/overlays/production
```

Pas in de overlay de namespace, image-tags en domeinnaam aan en maak het Secret
`hub-secrets` met `HUB_DATABASE_URL` en `HUB_JWT_PRIVATE_KEY` (zie de overlay).
PostgreSQL en Redis draaien in Kubernetes extern (managed dienst of operator).

## Ontwikkelen

Python (met [uv](https://docs.astral.sh/uv/)):

```bash
uv sync --all-packages
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Web:

```bash
cd web
npm install
npm test
npm run dev        # http://localhost:5173, /api gaat naar de gateway op :8080
```

## Een nieuwe app toevoegen

```bash
uv run python scripts/new_app.py --id agenda --name "Agenda" --description "Agenda's en afspraken"
uv sync --all-packages && uv run pytest
```

De generator maakt de app en zet hem in Docker Compose, Kubernetes en de uv-workspace.
Volledige handleiding: [docs/apps.md](docs/apps.md).

## Containers

Alle images zijn gehardend (Alpine, zonder shell en apk, niet-root). Bouwen:

```bash
uv run python scripts/images.py build
```

Meer: [docs/containers.md](docs/containers.md).
