# Werkafspraken myWork-Hub

- Communicatie, documentatie en commit-berichten in het **Nederlands**.
- **`docs/architecture.md` is leidend en altijd actueel.** Elke wijziging aan structuur,
  services, apps, deployment of tests werkt dat document bij in dezelfde commit,
  inclusief de mappenstructuur (sectie "Structuur van de repository").
- **`docs/apps.md` en `templates/` zijn de bron voor nieuwe apps.** Wijzigt het
  app-contract, de SDK, de templates, de generator (`scripts/new_app.py`) of de manier
  waarop apps in Docker/Kubernetes staan, dan worden templates, generator en
  `docs/apps.md` in dezelfde commit bijgewerkt. Pas `apps/hello` mee aan zodat hij gelijk
  blijft aan de templates (bewaakt door `tests/templates/`).
- **`docs/containers.md`** wordt bijgewerkt bij wijzigingen aan Dockerfiles,
  basisimages, `scripts/images.py` of de workflow `images.yml`.
- Nieuwe apps altijd met `scripts/new_app.py`, nooit met de hand kopiëren.
- `docker-compose.prod.yml` nooit met de hand wijzigen: `scripts/make_prod_compose.py`.
- `docs/security.md` bijwerken bij wijzigingen aan proxy, gateway, netwerken, firewall,
  auditlog of assistent. Elke nieuwe beheerhandeling schrijft een auditregel (core.audit).
- De assistent voert nooit wijzigende acties uit zonder bevestiging van de gebruiker en
  gebruikt altijd het token van de gebruiker.
- Containers alleen op Alpine met vaste versie, gehardend (geen shell/apk), als uid 65532
  in de draaifase.
- **Tests horen bij de code** en staan in de repository: nieuwe of gewijzigde code komt
  met tests in dezelfde commit (zie sectie "Tests" in `docs/architecture.md`).
- Apps zijn losse services; ze wisselen alleen gegevens uit via API's en events, nooit
  via elkaars database. De core is één service.
- Theming komt alleen uit de core; frontends gebruiken uitsluitend `--mw-*`-variabelen.
- Klantdata altijd met `tenant_id` en via `db.tenant_session(...)`; `system_session()`
  alleen waar klantoverstijgend echt nodig is (inloggen, aanmelden, CLI).
- De web-schil is een bureaublad met windowmanager (vensters, snap, verplaatsbare
  startbalk); logica in `web/src/wm/geometry.ts` en `windows.ts` met eigen tests.
- Docker Compose en Kubernetes blijven gelijk: een service die in de een wordt
  toegevoegd, komt ook in de ander (bewaakt door `tests/deploy/`).

## Controles vóór een commit

```bash
uv sync --all-packages
uv run ruff check . && uv run ruff format --check .
uv run pytest
cd web && npm test && npm run build
```
