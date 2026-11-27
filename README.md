# myWork-Hub

Een SaaS-hub voor klanten, in de geest van Nextcloud Hub. Apps draaien als losse services
en wisselen gegevens uit via API's en events; de core regelt klanten, gebruikers, het
app-register en het thema.

Zie [docs/architecture.md](docs/architecture.md) voor de architectuur, de volledige
mappenstructuur, de tests en de fasering.

## Structuur (kort)

```
packages/sdk/       Python-SDK (mywork_sdk) voor core en apps
services/core/      Core-service: theming, app-register (later: klanten, gebruikers, auth)
apps/hello/         Voorbeeld-app als losse service
web/                React-schil (Vite + TypeScript)
gateway/            nginx: enige publieke ingang
deploy/kubernetes/  Kustomize voor Kubernetes
tests/              Deployment- en integratietests
```

## Starten met Docker

```bash
cp .env.example .env
docker compose up -d --build
```

Daarna:

- http://localhost:8080 — de web-schil
- http://localhost:8080/api/core/docs — API-documentatie van de core
- http://localhost:8080/api/core/apps — status van de aangesloten apps
- http://localhost:8080/api/core/theme/theme.css — het actieve thema
- http://localhost:8080/api/apps/hello/docs — API-documentatie van de voorbeeld-app

## Draaien op Kubernetes

```bash
kubectl apply -k deploy/kubernetes/overlays/production
```

Pas in de overlay de namespace, image-tags en domeinnaam aan. PostgreSQL en Redis
draaien in Kubernetes extern (managed dienst of operator).

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

1. Maak `apps/<id>/` met een `manifest.yaml` en een FastAPI-service via
   `mywork_sdk.create_service(...)` (kijk naar `apps/hello`).
2. Voeg het pakket toe aan `members` in de root-`pyproject.toml`.
3. Voeg een service `app-<id>` toe in `docker-compose.yml` met `ROOT_PATH=/api/apps/<id>`.
4. Voeg `deploy/kubernetes/base/app-<id>.yaml` toe (kopieer `app-hello.yaml`) en zet
   het in `kustomization.yaml`.
5. Voeg `<id>=http://app-<id>:8000` toe aan `HUB_APPS` (`.env.example` en
   `deploy/kubernetes/base/config.yaml`).
6. Schrijf tests in `apps/<id>/tests/` en werk `docs/architecture.md` bij.

De gateway hoeft niet aangepast te worden. `tests/deploy/` controleert of Docker en
Kubernetes gelijk lopen.
