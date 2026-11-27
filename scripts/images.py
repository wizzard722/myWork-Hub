"""Overzicht en bouwen van alle container-images van myWork-Hub.

    uv run python scripts/images.py list                 # JSON (gebruikt door CI)
    uv run python scripts/images.py build                # alles lokaal bouwen
    uv run python scripts/images.py build --tag 0.2.0 --registry ghcr.io/wizzard722 --push

Apps worden automatisch gevonden in apps/<id>/; een nieuwe app hoeft hier niet
toegevoegd te worden.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DOCKERFILE = "docker/python-service.Dockerfile"


def discover(root: Path = ROOT) -> list[dict]:
    images = [
        {"name": "mywork-hub-gateway", "context": "gateway", "file": "gateway/Dockerfile",
         "build_args": {}},
        {"name": "mywork-hub-core", "context": ".", "file": PYTHON_DOCKERFILE,
         "build_args": {"PACKAGE": "mywork-core", "MODULE": "core.main"}},
        {"name": "mywork-hub-web", "context": "web", "file": "web/Dockerfile", "build_args": {}},
    ]  # fmt: skip
    for manifest in sorted((root / "apps").glob("*/manifest.yaml")):
        app_id = manifest.parent.name
        images.append(
            {
                "name": f"mywork-hub-app-{app_id}",
                "context": ".",
                "file": PYTHON_DOCKERFILE,
                "build_args": {
                    "PACKAGE": f"mywork-app-{app_id}",
                    "MODULE": f"{app_id.replace('-', '_')}.main",
                    "APP_DIR": f"apps/{app_id}",
                },
            }
        )
    return images


def for_github_matrix(images: list[dict]) -> list[dict]:
    """build-args als regels "KEY=waarde" voor docker/build-push-action."""
    return [
        {**img, "build_args": "\n".join(f"{k}={v}" for k, v in img["build_args"].items())}
        for img in images
    ]


def build(images: list[dict], tag: str, registry: str, push: bool) -> None:
    for img in images:
        ref = f"{registry.rstrip('/')}/{img['name']}" if registry else img["name"]
        cmd = ["docker", "build", "-f", img["file"], "-t", f"{ref}:{tag}"]
        for key, value in img["build_args"].items():
            cmd += ["--build-arg", f"{key}={value}"]
        cmd.append(img["context"])
        print("+", " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
        if push:
            subprocess.run(["docker", "push", f"{ref}:{tag}"], check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="images als JSON")
    b = sub.add_parser("build", help="images bouwen")
    b.add_argument("--tag", default="dev")
    b.add_argument("--registry", default="")
    b.add_argument("--push", action="store_true")
    b.add_argument("--only", nargs="*", help="alleen deze images (naam)")
    args = parser.parse_args(argv)

    images = discover()
    if args.command == "list":
        print(json.dumps(for_github_matrix(images)))
        return 0
    if args.only:
        images = [i for i in images if i["name"] in args.only]
    if args.push and not args.registry:
        parser.error("--push vereist --registry")
    build(images, args.tag, args.registry, args.push)
    return 0


if __name__ == "__main__":
    sys.exit(main())
