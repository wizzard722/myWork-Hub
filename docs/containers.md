# Containers

> **Levend document.** Bij wijzigingen aan Dockerfiles, basisimages, de
> image-workflow of `scripts/images.py` wordt dit document bijgewerkt.

## Gehardende basisimages

Alle images van myWork-Hub zijn gebouwd op **Chainguard-images** (Wolfi-basis):

| Image | Bouwfase | Draaifase |
| --- | --- | --- |
| `mywork-hub-core`, `mywork-hub-app-<id>` | `cgr.dev/chainguard/python:latest-dev` | `cgr.dev/chainguard/python:latest` |
| `mywork-hub-web` | `cgr.dev/chainguard/node:latest-dev` | `cgr.dev/chainguard/nginx:latest` |
| `mywork-hub-gateway` | — | `cgr.dev/chainguard/nginx:latest` |
| PostgreSQL, Redis (Docker Compose) | — | `cgr.dev/chainguard/postgres`, `cgr.dev/chainguard/redis` |

Wat "gehardend" hier betekent:

- **Minimaal:** alleen de runtime en de app; geen shell, geen package manager, geen
  extra tools. Minder software betekent minder kwetsbaarheden en minder
  aanvalsmogelijkheden.
- **Niet-root:** alles draait als uid **65532**.
- **Weinig bekende kwetsbaarheden:** Chainguard bouwt dagelijks opnieuw met de laatste
  beveiligingsupdates.
- **Read-only:** in Docker Compose (`read_only: true`) en Kubernetes
  (`readOnlyRootFilesystem: true`) is het bestandssysteem alleen-lezen; alleen `/tmp`
  is schrijfbaar.
- **Geen extra rechten:** alle Linux-capabilities zijn uitgeschakeld (`cap_drop: ALL`),
  `no-new-privileges`, en in Kubernetes het `RuntimeDefault` seccomp-profiel.

Omdat de draai-images geen shell hebben:

- starten Python-services met `python -m mywork_sdk.serve` (leest `MODULE`,
  `ROOT_PATH` en `PORT` uit de omgeving);
- staan `ENTRYPOINT`/`CMD` altijd in exec-vorm (`["..."]`);
- gebruiken healthchecks Python of HTTP-probes, geen `curl` of `sh`.

### Andere basisimages gebruiken

Elke Dockerfile heeft build-args voor de basisimages, bijvoorbeeld om een vaste versie
(digest) te gebruiken of over te stappen op Docker Hardened Images:

```bash
docker build -f docker/python-service.Dockerfile \
  --build-arg PYTHON_BUILD_IMAGE=cgr.dev/chainguard/python:latest-dev@sha256:... \
  --build-arg PYTHON_IMAGE=cgr.dev/chainguard/python:latest@sha256:... \
  --build-arg PACKAGE=mywork-core --build-arg MODULE=core.main .
```

| Dockerfile | Build-args |
| --- | --- |
| `docker/python-service.Dockerfile` | `PYTHON_BUILD_IMAGE`, `PYTHON_IMAGE`, `PACKAGE`, `MODULE`, `APP_DIR` |
| `web/Dockerfile` | `NODE_BUILD_IMAGE`, `NGINX_IMAGE` |
| `gateway/Dockerfile` | `NGINX_IMAGE` |

Let op: de gratis Chainguard-images zijn alleen beschikbaar met de tag `latest`. Voor
reproduceerbare productiebuilds is vastpinnen op digest aan te raden, met automatische
updates (bijv. Renovate).

## Images bouwen

```bash
uv run python scripts/images.py list                      # alle images (JSON)
uv run python scripts/images.py build                     # alles bouwen, tag "dev"
uv run python scripts/images.py build --only mywork-hub-core
uv run python scripts/images.py build --tag 0.2.0 --registry ghcr.io/wizzard722 --push
docker compose build                                      # zelfde images, tag "dev"
```

`scripts/images.py` vindt apps automatisch (elke map in `apps/` met een
`manifest.yaml`).

## Automatisch bouwen, scannen en publiceren

Workflow `.github/workflows/images.yml`:

| Gebeurtenis | Bouwen | Scannen (Trivy) | Publiceren naar `ghcr.io/wizzard722/` |
| --- | --- | --- | --- |
| Pull request / andere branch | ✅ | ✅ | — |
| Push naar `main` | ✅ | ✅ | tags `main`, `sha-<commit>` |
| Tag `v1.2.3` | ✅ | ✅ | tags `1.2.3`, `1.2`, `latest` |

- **Trivy** (als container `aquasec/trivy`) laat de build falen bij kwetsbaarheden met ernst HIGH of CRITICAL waarvoor
  een oplossing bestaat.
- Gepubliceerde images krijgen een **SBOM** (lijst van alle onderdelen) en
  **herkomstgegevens** (provenance), zodat na te gaan is waaruit en hoe ze gebouwd zijn.

De CI-workflow controleert daarnaast bij elke push dat elk image als uid 65532 draait en
geen shell bevat, en draait een rooktest van de hele stack met Docker Compose.

## Tests

| Test | Controleert |
| --- | --- |
| `tests/deploy/test_deployment_config.py` | Dockerfiles gebruiken Chainguard-basisimages, `USER 65532`, exec-vorm; Compose-services read-only, zonder capabilities; Kubernetes non-root, read-only, uid 65532 |
| `tests/templates/test_images.py` | `scripts/images.py` dekt alle gebouwde services, build-args gelijk aan Compose, alle images in de productie-overlay |
| `tests/integration/test_gateway.py` | De echte nginx-configuratie van gateway en web-schil (routering, SPA, beveiligingsheaders) |
| CI-job `docker` | Images: uid 65532, geen shell; rooktest van de stack |
| Workflow `Images` | Trivy-scan van elk image |
