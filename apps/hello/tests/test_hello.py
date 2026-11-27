from fastapi.testclient import TestClient

from hello.main import app

client = TestClient(app)


def test_manifest():
    data = client.get("/manifest").json()
    assert data["id"] == "hello"
    assert data["publishes"][0]["name"] == "hello.greeted"


def test_greet():
    assert client.get("/greetings/Paul").json() == {"message": "Hallo Paul, welkom bij myWork-Hub!"}


def test_whoami_requires_login():
    from fastapi.testclient import TestClient as Client

    from mywork_sdk.testing import fake_user, login_as

    assert client.get("/whoami").status_code == 401
    login_as(app, fake_user("admin", "acme"))
    try:
        assert Client(app).get("/whoami").json()["role"] == "admin"
    finally:
        app.dependency_overrides.clear()


def test_manifest_declares_tools():
    tools = {t["name"]: t for t in client.get("/manifest").json()["tools"]}
    assert tools["greet"]["path"] == "/greetings/{name}"
    assert tools["whoami"]["method"] == "GET"
