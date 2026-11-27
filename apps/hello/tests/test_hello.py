from fastapi.testclient import TestClient

from hello.main import app

client = TestClient(app)


def test_manifest():
    data = client.get("/manifest").json()
    assert data["id"] == "hello"
    assert data["publishes"][0]["name"] == "hello.greeted"


def test_greet():
    assert client.get("/greetings/Paul").json() == {"message": "Hallo Paul, welkom bij myWork-Hub!"}
