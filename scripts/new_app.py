"""Maak een nieuwe app voor myWork-Hub op basis van de templates.

Gebruik:
    uv run python scripts/new_app.py --id agenda --name "Agenda" \
        --description "Agenda's en afspraken"

Wat het doet (zie docs/apps.md):
1. apps/<id>/ aanmaken uit templates/app/
2. het pakket toevoegen aan de uv-workspace (pyproject.toml)
3. service app-<id> toevoegen aan docker-compose.yml
4. deploy/kubernetes/base/app-<id>.yaml aanmaken en opnemen in kustomization.yaml
5. de image toevoegen aan de productie-overlay
6. de app registreren in HUB_APPS (Docker Compose en Kubernetes)
7. docker-compose.prod.yml opnieuw genereren
8. uv lock (tenzij --no-lock)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

APP_ID_PATTERN = r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$"
RESERVED_IDS = {"core", "web", "gateway", "api", "admin"}
DEFAULT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_MARKER = "  # <<< einde apps"


class AppError(Exception):
    pass


def placeholders(app_id: str, name: str, description: str) -> dict[str, str]:
    return {
        "__APP_ID__": app_id,
        "__APP_MODULE__": app_id.replace("-", "_"),
        "__APP_NAME__": name,
        "__APP_DESCRIPTION__": description,
    }


def render(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace(key, value)
    return text


def validate(root: Path, app_id: str, name: str) -> None:
    if not re.fullmatch(APP_ID_PATTERN, app_id) or "--" in app_id:
        raise AppError(
            f"Ongeldige app-id {app_id!r}: 3-40 tekens, kleine letters, cijfers en "
            "koppeltekens, beginnend met een letter."
        )
    if app_id in RESERVED_IDS:
        raise AppError(f"App-id {app_id!r} is gereserveerd.")
    if not name.strip() or "\n" in name or ":" in name:
        raise AppError("Geef een naam op van één regel, zonder dubbele punt.")
    if (root / "apps" / app_id).exists():
        raise AppError(f"apps/{app_id} bestaat al.")


def copy_app_template(root: Path, app_id: str, values: dict[str, str]) -> list[Path]:
    source = root / "templates" / "app"
    target = root / "apps" / app_id
    created = []
    for path in sorted(source.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        relative = render(str(path.relative_to(source)), values)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render(path.read_text(encoding="utf-8"), values), encoding="utf-8")
        created.append(destination)
    return created


def add_workspace_member(root: Path, app_id: str) -> None:
    path = root / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"members = \[(.*?)\]", text, re.S)
    if not match:
        raise AppError("Kan 'members' niet vinden in pyproject.toml")
    members = re.findall(r'"([^"]+)"', match.group(1))
    members.append(f"apps/{app_id}")
    new = "members = [" + ", ".join(f'"{m}"' for m in members) + "]"
    path.write_text(text[: match.start()] + new + text[match.end() :], encoding="utf-8")


def append_to_hub_apps(path: Path, app_id: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"^(\s*HUB_APPS:\s*)(\S*)\s*$", re.M)
    match = pattern.search(text)
    if not match:
        raise AppError(f"Geen HUB_APPS-regel gevonden in {path}")
    entries = [e for e in match.group(2).split(",") if e]
    entries.append(f"{app_id}=http://app-{app_id}:8000")
    line = match.group(1) + ",".join(entries)
    path.write_text(text[: match.start()] + line + text[match.end() :], encoding="utf-8")


def add_compose_service(root: Path, values: dict[str, str]) -> None:
    path = root / "docker-compose.yml"
    text = path.read_text(encoding="utf-8")
    if COMPOSE_MARKER not in text:
        raise AppError("Markering voor apps ontbreekt in docker-compose.yml")
    snippet = render((root / "templates/deploy/compose-service.yaml").read_text(), values)
    path.write_text(text.replace(COMPOSE_MARKER, snippet + COMPOSE_MARKER, 1), encoding="utf-8")
    append_to_hub_apps(path, values["__APP_ID__"])


def add_kubernetes(root: Path, values: dict[str, str]) -> None:
    app_id = values["__APP_ID__"]
    base = root / "deploy/kubernetes/base"
    manifest = render((root / "templates/deploy/kubernetes-app.yaml").read_text(), values)
    (base / f"app-{app_id}.yaml").write_text(manifest, encoding="utf-8")

    kustomization = base / "kustomization.yaml"
    text = kustomization.read_text(encoding="utf-8").rstrip("\n") + "\n"
    kustomization.write_text(text + f"  - app-{app_id}.yaml\n", encoding="utf-8")

    append_to_hub_apps(base / "config.yaml", app_id)

    overlay = root / "deploy/kubernetes/overlays/production/kustomization.yaml"
    lines = overlay.read_text(encoding="utf-8").splitlines()
    app_lines = [i for i, line in enumerate(lines) if "name: mywork-hub-app-" in line]
    if not app_lines:
        raise AppError("Geen app-images gevonden in de productie-overlay")
    template_line = lines[app_lines[-1]]
    new_line = re.sub(r"mywork-hub-app-[a-z0-9-]+", f"mywork-hub-app-{app_id}", template_line)
    lines.insert(app_lines[-1] + 1, new_line)
    overlay.write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_app(root: Path, app_id: str, name: str, description: str) -> list[Path]:
    validate(root, app_id, name)
    values = placeholders(app_id, name.strip(), description.strip() or name.strip())
    created = copy_app_template(root, app_id, values)
    add_workspace_member(root, app_id)
    add_compose_service(root, values)
    add_kubernetes(root, values)
    # Productie-compose opnieuw genereren (zelfde map als dit script).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import make_prod_compose

    make_prod_compose.write(root)
    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Maak een nieuwe myWork-Hub-app.")
    parser.add_argument("--id", required=True, dest="app_id", help="app-id, bijv. agenda")
    parser.add_argument("--name", required=True, help='weergavenaam, bijv. "Agenda"')
    parser.add_argument("--description", default="", help="korte omschrijving")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--no-lock", action="store_true", help="uv lock overslaan")
    args = parser.parse_args(argv)

    try:
        create_app(args.root, args.app_id, args.name, args.description)
    except AppError as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        return 1

    if not args.no_lock:
        subprocess.run(["uv", "lock"], cwd=args.root, check=True)

    print(
        f"""App '{args.app_id}' aangemaakt.

Volgende stappen:
  uv sync --all-packages
  uv run pytest apps/{args.app_id} tests/
  docker compose up -d --build app-{args.app_id} core

Bouw daarna de echte API in apps/{args.app_id}/src/ en werk het manifest bij.
Handleiding: docs/apps.md"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
