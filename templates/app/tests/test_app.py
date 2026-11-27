from fastapi.testclient import TestClient

from __APP_MODULE__.main import app
from mywork_sdk.testing import fake_user, login_as

client = TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_manifest():
    data = client.get("/manifest").json()
    assert data["id"] == "__APP_ID__"
    assert data["name"] == "__APP_NAME__"
    assert {t["name"] for t in data["tools"]} == {"list_items", "add_item"}


def test_items_require_login():
    assert client.get("/items").status_code == 401


def test_list_items():
    login_as(app, fake_user("member"))
    response = client.get("/items")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_add_item_requires_admin():
    login_as(app, fake_user("member"))
    assert client.post("/items", json={"title": "x"}).status_code == 403
    login_as(app, fake_user("admin"))
    assert client.post("/items", json={"title": "x"}).status_code == 201
