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
- Containers alleen op gehardende basisimages (Chainguard), als uid 65532, zonder shell
  in de draaifase.
- **Tests horen bij de code** en staan in de repository: nieuwe of gewijzigde code komt
  met tests in dezelfde commit (zie sectie "Tests" in `docs/architecture.md`).
- Apps zijn losse services; ze wisselen alleen gegevens uit via API's en events, nooit
  via elkaars database. De core is één service.
- Theming komt alleen uit de core; frontends gebruiken uitsluitend `--mw-*`-variabelen.
- Docker Compose en Kubernetes blijven gelijk: een service die in de een wordt
  toegevoegd, komt ook in de ander (bewaakt door `tests/deploy/`).

## Controles vóór een commit

```bash
uv sync --all-packages
uv run ruff check . && uv run ruff format --check .
uv run pytest
cd web && npm test && npm run build
```
