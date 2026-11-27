import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import images  # noqa: E402
import yaml  # noqa: E402


def test_every_compose_service_with_build_has_an_image():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    built = {name for name, svc in compose["services"].items() if "build" in svc}
    names = {img["name"].removeprefix("mywork-hub-") for img in images.discover()}
    assert built == names


def test_build_args_match_compose():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    for img in images.discover():
        service = compose["services"][img["name"].removeprefix("mywork-hub-")]
        build = service["build"]
        compose_args = build.get("args", {}) if isinstance(build, dict) else {}
        assert compose_args == img["build_args"], img["name"]


def test_matrix_is_json(capsys):
    assert images.main(["list"]) == 0
    matrix = json.loads(capsys.readouterr().out)
    core = next(i for i in matrix if i["name"] == "mywork-hub-core")
    assert core["build_args"] == "PACKAGE=mywork-core\nMODULE=core.main"


def test_kubernetes_overlay_lists_every_image():
    overlay = (ROOT / "deploy/kubernetes/overlays/production/kustomization.yaml").read_text()
    for img in images.discover():
        if img["name"] == "mywork-hub-proxy":
            continue  # in Kubernetes is de Ingress-controller de reverse proxy
        assert f"name: {img['name']}," in overlay, img["name"]


def test_prod_compose_is_up_to_date():
    import make_prod_compose

    assert (ROOT / "docker-compose.prod.yml").read_text() == make_prod_compose.build(ROOT), (
        "Voer uit: uv run python scripts/make_prod_compose.py"
    )


def test_prod_compose_has_all_images_and_no_builds():
    prod = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text())
    dev = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert set(prod["services"]) == set(dev["services"])
    for name, service in prod["services"].items():
        assert "build" not in service, name
        assert service["image"], name
    for img in images.discover():
        assert any(img["name"] + ":" in s["image"] for s in prod["services"].values()), img["name"]
    core_env = prod["services"]["core"]["environment"]
    assert core_env["HUB_ENVIRONMENT"] == "production"
    assert ":?" in core_env["HUB_JWT_PRIVATE_KEY"]
    assert "change-me" not in (ROOT / "docker-compose.prod.yml").read_text()
