"""Maak docker-compose.prod.yml uit docker-compose.yml.

    uv run python scripts/make_prod_compose.py          # schrijven
    uv run python scripts/make_prod_compose.py --check  # controleren of hij actueel is

De productieversie bevat **alle benodigde images** (hub, PostgreSQL, Redis, proxy,
assistent, apps) als kant-en-klare images uit de registry; er wordt niets gebouwd.
Verschillen met de ontwikkelversie:
- eigen images uit ${HUB_REGISTRY}/<naam>:${HUB_VERSION} (versie verplicht);
- wachtwoorden, domein en JWT-sleutel verplicht (geen standaardwaarden);
- TLS standaard via Let's Encrypt (ondemand) en HUB_ENVIRONMENT=production.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docker-compose.prod.yml"

HEADER = """\
# GEGENEREERD door scripts/make_prod_compose.py uit docker-compose.yml — niet met de hand
# wijzigen. Productie-opstelling met alle benodigde images (niets bouwen):
#
#   cp .env.example .env        # vul HUB_DOMAIN, HUB_VERSION, wachtwoorden en sleutel in
#   docker compose -f docker-compose.prod.yml pull
#   docker compose -f docker-compose.prod.yml up -d
#
# Zie docs/containers.md en docs/security.md.
"""

REQUIRED = {
    "POSTGRES_PASSWORD": "Zet POSTGRES_PASSWORD in .env",
    "REDIS_PASSWORD": "Zet REDIS_PASSWORD in .env",
    "HUB_DOMAIN": "Zet HUB_DOMAIN in .env, bijv. hub.example.com",
    "HUB_JWT_PRIVATE_KEY": "Zet HUB_JWT_PRIVATE_KEY in .env (python -m core.cli generate-key)",
    "ACME_EMAIL": "Zet ACME_EMAIL in .env (voor Let's Encrypt)",
}
DEFAULTS = {"HUB_TLS": "ondemand"}
IMAGE = "${HUB_REGISTRY:-ghcr.io/wizzard722}/%s:${HUB_VERSION:?Zet HUB_VERSION, bijv. 0.1.0}"


def _fix_vars(value):
    if isinstance(value, str):
        for name, message in REQUIRED.items():
            pattern = r"\$\{" + name + r"(:-[^}]*)?\}"
            value = re.sub(pattern, f"${{{name}:?{message}}}", value)
        for name, default in DEFAULTS.items():
            value = re.sub(r"\$\{" + name + r":-[^}]*\}", f"${{{name}:-{default}}}", value)
        return value
    if isinstance(value, list):
        return [_fix_vars(v) for v in value]
    if isinstance(value, dict):
        return {k: _fix_vars(v) for k, v in value.items()}
    return value


def build(root: Path = ROOT) -> str:
    data = yaml.safe_load((root / "docker-compose.yml").read_text())
    data = {k: v for k, v in data.items() if not k.startswith("x-")}
    for service in data["services"].values():
        if "build" in service:
            del service["build"]
            service["image"] = IMAGE % service["image"].split(":")[0]
            service["pull_policy"] = "always"
    core = data["services"]["core"]
    core["environment"]["HUB_ENVIRONMENT"] = "production"
    core["environment"]["HUB_JWT_PRIVATE_KEY"] = "${HUB_JWT_PRIVATE_KEY}"
    data = _fix_vars(data)
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120)
    return HEADER + "\n" + body


def write(root: Path = ROOT) -> None:
    (root / "docker-compose.prod.yml").write_text(build(root))


def main(argv: list[str]) -> int:
    content = build()
    if "--check" in argv:
        if not TARGET.exists() or TARGET.read_text() != content:
            print("docker-compose.prod.yml niet actueel; draai scripts/make_prod_compose.py")
            return 1
        return 0
    TARGET.write_text(content)
    print(f"{TARGET.name} geschreven.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
