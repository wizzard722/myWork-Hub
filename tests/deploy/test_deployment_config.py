"""Controles op de deployment-configuratie (Docker Compose en Kubernetes).

Deze tests draaien zonder cluster of Docker: ze lezen de YAML-bestanden en bewaken dat
beide manieren van draaien dezelfde services hebben en aan de basisregels voldoen.
"""

import os
from pathlib import Path

import pytest
import yaml

# HUB_REPO_ROOT: gebruikt door de generator-test om een kopie van de repo te controleren.
ROOT = Path(os.environ.get("HUB_REPO_ROOT") or Path(__file__).resolve().parents[2])
K8S_BASE = ROOT / "deploy" / "kubernetes" / "base"
K8S_OVERLAYS = ROOT / "deploy" / "kubernetes" / "overlays"


def load_docs(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [doc for doc in yaml.safe_load_all(fh) if doc]


def k8s_objects() -> list[dict]:
    kustomization = load_docs(K8S_BASE / "kustomization.yaml")[0]
    objects: list[dict] = []
    for resource in kustomization["resources"]:
        objects.extend(load_docs(K8S_BASE / resource))
    return objects


def by_kind(kind: str) -> dict[str, dict]:
    return {o["metadata"]["name"]: o for o in k8s_objects() if o["kind"] == kind}


def compose() -> dict:
    return load_docs(ROOT / "docker-compose.yml")[0]


# --- Kubernetes ---------------------------------------------------------------------


def test_kustomization_lists_every_manifest():
    listed = set(load_docs(K8S_BASE / "kustomization.yaml")[0]["resources"])
    on_disk = {p.name for p in K8S_BASE.glob("*.yaml")} - {"kustomization.yaml"}
    assert listed == on_disk


def test_overlays_reference_existing_resources():
    for kustomization in K8S_OVERLAYS.glob("*/kustomization.yaml"):
        for resource in load_docs(kustomization)[0]["resources"]:
            assert (kustomization.parent / resource).exists(), f"{kustomization}: {resource}"


DEPLOYMENTS = sorted(by_kind("Deployment"))


@pytest.mark.parametrize("name", DEPLOYMENTS)
def test_deployment_selector_matches_template(name):
    dep = by_kind("Deployment")[name]
    selector = dep["spec"]["selector"]["matchLabels"]
    labels = dep["spec"]["template"]["metadata"]["labels"]
    assert selector.items() <= labels.items()


@pytest.mark.parametrize("name", DEPLOYMENTS)
def test_deployment_is_production_ready(name):
    spec = by_kind("Deployment")[name]["spec"]
    pod = spec["template"]["spec"]
    assert spec["replicas"] >= 2, "minimaal 2 replica's voor beschikbaarheid"
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["runAsUser"] == 65532, "uid van de gehardende images"
    assert pod["automountServiceAccountToken"] is False
    for container in pod["containers"]:
        assert "readinessProbe" in container and "livenessProbe" in container
        assert "requests" in container["resources"]
        assert "memory" in container["resources"]["limits"]
        assert container["securityContext"]["allowPrivilegeEscalation"] is False
        assert container["securityContext"]["readOnlyRootFilesystem"] is True
        assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]


@pytest.mark.parametrize("name", DEPLOYMENTS)
def test_every_deployment_has_service_hpa_and_pdb(name):
    assert name in by_kind("Service")
    assert by_kind("HorizontalPodAutoscaler")[name]["spec"]["scaleTargetRef"]["name"] == name
    assert name in by_kind("PodDisruptionBudget")


def test_services_select_existing_deployments():
    deployments = by_kind("Deployment")
    for name, service in by_kind("Service").items():
        selector = service["spec"]["selector"]
        labels = deployments[name]["spec"]["template"]["metadata"]["labels"]
        assert selector.items() <= labels.items(), name


def test_ingress_only_exposes_gateway():
    for ingress in by_kind("Ingress").values():
        for rule in ingress["spec"]["rules"]:
            for path in rule["http"]["paths"]:
                assert path["backend"]["service"]["name"] == "gateway"


# --- Docker Compose en Kubernetes gelijk houden -------------------------------------


def test_compose_and_kubernetes_have_same_services():
    infra = {"postgres", "redis"}  # in Kubernetes extern (managed of operator)
    compose_services = set(compose()["services"]) - infra
    assert compose_services == set(DEPLOYMENTS)


def test_app_services_follow_naming_convention():
    """De gateway routeert /api/apps/<id> naar app-<id>: de namen moeten kloppen."""
    for name, service in compose()["services"].items():
        if not name.startswith("app-"):
            continue
        app_id = name.removeprefix("app-")
        assert service["environment"]["ROOT_PATH"] == f"/api/apps/{app_id}"
        k8s_env = {
            e["name"]: e.get("value")
            for e in by_kind("Deployment")[name]["spec"]["template"]["spec"]["containers"][0]["env"]
        }
        assert k8s_env["ROOT_PATH"] == f"/api/apps/{app_id}"


def test_hub_apps_point_to_known_services():
    hub_apps = by_kind("ConfigMap")["hub-config"]["data"]["HUB_APPS"]
    for item in hub_apps.split(","):
        app_id, _, url = item.partition("=")
        assert url == f"http://app-{app_id}:8000"
        assert f"app-{app_id}" in compose()["services"]


def test_compose_services_are_hardened():
    for name, service in compose()["services"].items():
        if name in {"postgres", "redis"}:
            assert service["image"].startswith("cgr.dev/chainguard/"), name
            continue
        assert service.get("read_only") is True, name
        assert service.get("cap_drop") == ["ALL"], name
        assert "no-new-privileges:true" in service.get("security_opt", []), name


def test_dockerfiles_use_hardened_base_images():
    dockerfiles = [
        ROOT / "docker" / "python-service.Dockerfile",
        ROOT / "gateway" / "Dockerfile",
        ROOT / "web" / "Dockerfile",
    ]
    for dockerfile in dockerfiles:
        text = dockerfile.read_text()
        base_args = [
            line for line in text.splitlines() if line.startswith("ARG ") and "_IMAGE=" in line
        ]
        assert base_args, dockerfile
        for line in base_args:
            assert "=cgr.dev/chainguard/" in line, f"{dockerfile}: {line}"
        assert "USER 65532" in text, dockerfile
        assert "ENTRYPOINT [" in text, f"{dockerfile}: exec-vorm nodig (geen shell in image)"
