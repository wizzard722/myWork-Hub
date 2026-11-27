# Containers

> **Levend document.** Bij wijzigingen aan Dockerfiles, basisimages, de
> image-workflow of `scripts/images.py` wordt dit document bijgewerkt.

## Gehardende basisimages (Alpine)

Alle images van myWork-Hub zijn gebouwd op **Alpine Linux** met vaste versies:

| Image | Bouwfase | Draaifase |
| --- | --- | --- |
| `mywork-hub-core`, `mywork-hub-assistant`, `mywork-hub-app-<id>` | `python:3.13-alpine3.22` | `python:3.13-alpine3.22`, gehardend |
| `mywork-hub-web` | `node:22-alpine3.22` | `nginx:1.28-alpine`, gehardend |
| `mywork-hub-gateway` | — | `nginx:1.28-alpine`, gehardend |
| `mywork-hub-proxy` | — | `caddy:2.10-alpine`, gehardend |
| PostgreSQL, Redis (onderdeel van de hub) | — | `postgres:17-alpine`, `redis:7.4-alpine` (officieel, niet-root) |

Waarom Alpine: klein, breed beschikbaar (Docker Hub), vaste versies en digests mogelijk,
en goed te harden. In de draaifase van onze eigen images wordt Alpine verder
uitgekleed:

- **Updates:** `apk upgrade` bij het bouwen (build-arg `APK_UPGRADE=true`, standaard aan).
- **Geen package manager:** `apk` en de index worden verwijderd.
- **Geen shell:** BusyBox (en daarmee `/bin/sh`) wordt als laatste verwijderd; ook
  `pip` en het entrypoint-script van nginx zijn weg.
- **Geen setuid/setgid-bestanden.**
- **Niet-root:** uid/gid **65532**.
- **Read-only:** in Docker Compose (`read_only: true`) en Kubernetes
  (`readOnlyRootFilesystem: true`) is het bestandssysteem alleen-lezen; alleen `/tmp`
  (en voor PostgreSQL `/var/run/postgresql`) is schrijfbaar.
- **Geen extra rechten:** `cap_drop: ALL`, `no-new-privileges`, in Kubernetes het
  `RuntimeDefault` seccomp-profiel. Caddy bindt 80/443 als niet-root via de sysctl
  `net.ipv4.ip_unprivileged_port_start=0` (de file-capability op het binary is
  verwijderd).

Omdat de draai-images geen shell hebben:

- starten Python-services met `python -m mywork_sdk.serve` (leest `MODULE`,
  `ROOT_PATH` en `PORT` uit de omgeving);
- staan `ENTRYPOINT`/`CMD` altijd in exec-vorm (`["..."]`);
- gebruiken healthchecks Python of HTTP-probes, geen `curl` of `sh`;
- draai je beheeropdrachten met `docker compose exec core python -m core.cli ...`.

### Andere basisimages of vaste digests

Elke Dockerfile heeft build-args voor de basisimages, bijvoorbeeld om op een digest
vast te pinnen:

```bash
docker build -f docker/python-service.Dockerfile \
  --build-arg PYTHON_IMAGE=python:3.13-alpine3.22@sha256:... \
  --build-arg PACKAGE=mywork-core --build-arg MODULE=core.main .
```

| Dockerfile | Build-args |
| --- | --- |
| `docker/python-service.Dockerfile` | `PYTHON_IMAGE`, `PACKAGE`, `MODULE`, `APP_DIR`, `APK_UPGRADE` |
| `web/Dockerfile` | `NODE_BUILD_IMAGE`, `NGINX_IMAGE`, `APK_UPGRADE` |
| `gateway/Dockerfile` | `NGINX_IMAGE`, `APK_UPGRADE` |
| `proxy/Dockerfile` | `CADDY_IMAGE`, `APK_UPGRADE` |

### Bouwen achter een proxy met eigen CA

De Dockerfiles accepteren optioneel een CA-certificaat als build-secret; het komt niet
in het image:

```bash
docker build --secret id=ca_bundle,src=ca.crt ...
```

## Images bouwen

```bash
uv run python scripts/images.py list                      # alle images (JSON)
uv run python scripts/images.py build                     # alles bouwen, tag "dev"
uv run python scripts/images.py build --only mywork-hub-core
uv run python scripts/images.py build --only mywork-hub-proxy
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
geen shell of apk bevat, en draait een rooktest van de hele stack met Docker Compose.

## Tests

| Test | Controleert |
| --- | --- |
| `tests/deploy/test_deployment_config.py` | Dockerfiles op Alpine met vaste versie, `USER 65532`, exec-vorm, apk en shell verwijderd; Compose-services read-only, niet-root, zonder capabilities; Kubernetes non-root, read-only |
| `tests/templates/test_images.py` | `scripts/images.py` dekt alle gebouwde services, build-args gelijk aan Compose, alle images in de productie-overlay |
| `tests/integration/test_gateway.py` | De echte nginx-configuratie van gateway en web-schil (routering, SPA, beveiligingsheaders) |
| CI-job `docker` | Images: uid 65532, geen shell; rooktest van de stack |
| Workflow `Images` | Trivy-scan van elk image |
