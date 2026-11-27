from fastapi.testclient import TestClient

from __APP_MODULE__.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_manifest():
    data = client.get("/manifest").json()
    assert data["id"] == "__APP_ID__"
    assert data["name"] == "__APP_NAME__"


def test_list_items():
    response = client.get("/items")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
