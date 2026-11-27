"""Tests voor de app-template en de generator (scripts/new_app.py).

- De bestaande app ``hello`` moet overeenkomen met de templates, zodat template en
  werkelijkheid niet uit elkaar lopen.
- De generator wordt uitgevoerd op een kopie van de repository; daarna moeten de
  nieuwe app-tests en alle deployment-tests slagen.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import new_app  # noqa: E402

HELLO = new_app.placeholders("hello", "Hello", "")


def test_hello_kubernetes_matches_template():
    rendered = new_app.render((ROOT / "templates/deploy/kubernetes-app.yaml").read_text(), HELLO)
    assert rendered == (ROOT / "deploy/kubernetes/base/app-hello.yaml").read_text()


def test_hello_compose_matches_template():
    rendered = new_app.render((ROOT / "templates/deploy/compose-service.yaml").read_text(), HELLO)
    assert rendered in (ROOT / "docker-compose.yml").read_text()


def test_id_pattern_matches_sdk():
    from mywork_sdk.manifest import APP_ID_PATTERN

    assert new_app.APP_ID_PATTERN == APP_ID_PATTERN


@pytest.mark.parametrize("bad_id", ["A", "ab", "1app", "app-", "app_x", "core", "hello", "a--b"])
def test_rejects_invalid_or_existing_ids(bad_id):
    with pytest.raises(new_app.AppError):
        new_app.validate(ROOT, bad_id, "Naam")


@pytest.fixture
def repo_copy(tmp_path):
    ignore = shutil.ignore_patterns(
        ".git", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache", ".ruff_cache"
    )
    target = tmp_path / "repo"
    shutil.copytree(ROOT, target, ignore=ignore)
    return target


def test_generator_creates_working_app(repo_copy):
    exit_code = new_app.main(
        [
            "--id", "agenda-plus",
            "--name", "Agenda Plus",
            "--description", "Agenda's en afspraken",
            "--root", str(repo_copy),
            "--no-lock",
        ]
    )  # fmt: skip
    assert exit_code == 0

    app_dir = repo_copy / "apps/agenda-plus"
    assert (app_dir / "src/agenda_plus/main.py").exists()
    manifest = yaml.safe_load((app_dir / "manifest.yaml").read_text())
    assert manifest["id"] == "agenda-plus"
    assert manifest["description"] == "Agenda's en afspraken"
    assert not list(app_dir.rglob("*__APP_*"))
    assert "__APP_" not in "".join(p.read_text() for p in app_dir.rglob("*") if p.is_file())

    pyproject = (repo_copy / "pyproject.toml").read_text()
    assert '"apps/agenda-plus"' in pyproject

    compose = yaml.safe_load((repo_copy / "docker-compose.yml").read_text())
    service = compose["services"]["app-agenda-plus"]
    assert service["environment"]["ROOT_PATH"] == "/api/apps/agenda-plus"
    assert service["build"]["args"]["MODULE"] == "agenda_plus.main"
    hub_apps = compose["services"]["core"]["environment"]["HUB_APPS"]
    assert hub_apps.endswith(",agenda-plus=http://app-agenda-plus:8000")

    prod = yaml.safe_load((repo_copy / "docker-compose.prod.yml").read_text())
    assert "mywork-hub-app-agenda-plus:" in prod["services"]["app-agenda-plus"]["image"]

    overlay = (repo_copy / "deploy/kubernetes/overlays/production/kustomization.yaml").read_text()
    assert "ghcr.io/wizzard722/mywork-hub-app-agenda-plus" in overlay

    env = {**os.environ, "PYTHONPATH": str(app_dir / "src")}
    # De tests van de nieuwe app slagen direct.
    app_tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(app_dir / "tests")],
        cwd=repo_copy,
        env=env,
        capture_output=True,
        text=True,
    )
    assert app_tests.returncode == 0, app_tests.stdout + app_tests.stderr

    # De gegenereerde code voldoet aan de codestijl.
    lint = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "apps/agenda-plus"],
        cwd=repo_copy,
        capture_output=True,
        text=True,
    )
    assert lint.returncode == 0, lint.stdout + lint.stderr

    # Docker Compose en Kubernetes blijven consistent.
    deploy_tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/deploy"],
        cwd=repo_copy,
        env={**os.environ, "HUB_REPO_ROOT": str(repo_copy)},
        capture_output=True,
        text=True,
    )
    assert deploy_tests.returncode == 0, deploy_tests.stdout + deploy_tests.stderr
    assert re.search(r"\d+ passed", deploy_tests.stdout)


def test_generator_refuses_existing_app(repo_copy, capsys):
    args = ["--id", "hello", "--name", "Hello", "--root", str(repo_copy), "--no-lock"]
    assert new_app.main(args) == 1
    assert "bestaat al" in capsys.readouterr().err
