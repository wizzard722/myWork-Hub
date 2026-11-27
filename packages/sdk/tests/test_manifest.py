import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mywork_sdk import AppManifest, create_service, load_manifest


def test_load_manifest(tmp_path):
    path = tmp_path / "manifest.yaml"
    path.write_text(
        "id: demo-app\nname: Demo\nversion: 1.0.0\npublishes:\n  - name: demo-app.thing_created\n"
    )
    manifest = load_manifest(path)
    assert manifest.id == "demo-app"
    assert manifest.publishes[0].name == "demo-app.thing_created"


@pytest.mark.parametrize("bad_id", ["A", "1app", "app_", "-app", "x"])
def test_invalid_app_id(bad_id):
    with pytest.raises(ValidationError):
        AppManifest(id=bad_id, name="x", version="1")


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        AppManifest(id="demo", name="x", version="1", unknown=True)


def test_service_endpoints():
    manifest = AppManifest(id="demo", name="Demo", version="1.0.0")
    client = TestClient(create_service(name="demo", version="1.0.0", manifest=manifest))
    assert client.get("/health").json() == {"status": "ok", "service": "demo", "version": "1.0.0"}
    assert client.get("/manifest").json()["id"] == "demo"


def test_service_without_manifest():
    client = TestClient(create_service(name="core", version="0.1.0"))
    assert client.get("/manifest").status_code == 404
