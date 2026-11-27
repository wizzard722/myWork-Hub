"""Hulpfuncties voor de core-tests (signup, headers)."""

from fastapi.testclient import TestClient

BASE_DOMAIN = "hub.test"
PASSWORD = "een-lang-wachtwoord"


def signup(client: TestClient, slug: str, email: str | None = None) -> dict:
    response = client.post(
        "/signup",
        json={
            "tenant_name": slug.capitalize() + " BV",
            "slug": slug,
            "email": email or f"eigenaar@{slug}.nl",
            "display_name": "Eigenaar " + slug,
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['access_token']}"}


def host(slug: str) -> dict[str, str]:
    return {"Host": f"{slug}.{BASE_DOMAIN}"}
