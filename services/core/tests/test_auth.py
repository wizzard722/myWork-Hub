"""Inloggen, sessies en klantherkenning (vereist PostgreSQL, zie conftest.py)."""

import jwt
from core_testkit import PASSWORD, auth, host, signup

CSRF = {"X-Hub-Request": "1"}


def login(client, email, password=PASSWORD, headers=None, **extra):
    return client.post(
        "/auth/login", json={"email": email, "password": password, **extra}, headers=headers or {}
    )


def test_signup_returns_session(client):
    session = signup(client, "acme")
    assert session["tenant"] == {"slug": "acme", "name": "Acme BV"}
    assert session["user"]["role"] == "owner"
    assert "mw_refresh" in client.cookies


def test_login_without_subdomain_uses_account_tenant(client):
    signup(client, "acme")
    response = login(client, "Eigenaar@Acme.nl")  # hoofdletters maken niet uit
    assert response.status_code == 200
    assert response.json()["tenant"]["slug"] == "acme"


def test_login_on_own_subdomain(client):
    signup(client, "acme")
    assert login(client, "eigenaar@acme.nl", headers=host("acme")).status_code == 200


def test_login_on_other_tenant_subdomain_fails(client):
    signup(client, "acme")
    signup(client, "beta")
    response = login(client, "eigenaar@acme.nl", headers=host("beta"))
    assert response.status_code == 401


def test_wrong_password_and_unknown_email_same_answer(client):
    signup(client, "acme")
    wrong = login(client, "eigenaar@acme.nl", "verkeerd-wachtwoord")
    unknown = login(client, "niemand@acme.nl")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_me_requires_token(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer onzin"}).status_code == 401


def test_me(client):
    session = signup(client, "acme")
    me = client.get("/me", headers=auth(session)).json()
    assert me["email"] == "eigenaar@acme.nl"


def test_token_not_valid_on_other_tenant_subdomain(client):
    session = signup(client, "acme")
    signup(client, "beta")
    response = client.get("/me", headers={**auth(session), **host("beta")})
    assert response.status_code == 403


def test_refresh_rotates_and_detects_reuse(client):
    signup(client, "acme")
    first = client.cookies.get("mw_refresh")
    refreshed = client.post("/auth/refresh", headers=CSRF)
    assert refreshed.status_code == 200
    second = client.cookies.get("mw_refresh")
    assert second and second != first

    # Oud token opnieuw gebruiken = diefstal: hele sessie ingetrokken.
    client.cookies.set("mw_refresh", first)
    assert client.post("/auth/refresh", headers=CSRF).status_code == 401
    client.cookies.set("mw_refresh", second)
    assert client.post("/auth/refresh", headers=CSRF).status_code == 401


def test_refresh_requires_csrf_header(client):
    signup(client, "acme")
    assert client.post("/auth/refresh").status_code == 403


def test_logout_ends_session(client):
    signup(client, "acme")
    token = client.cookies.get("mw_refresh")
    assert client.post("/auth/logout", headers=CSRF).status_code == 204
    client.cookies.set("mw_refresh", token)
    assert client.post("/auth/refresh", headers=CSRF).status_code == 401


def test_refresh_cookie_flags(client):
    response = client.post(
        "/signup",
        json={
            "tenant_name": "Acme",
            "slug": "acme",
            "email": "a@acme.nl",
            "display_name": "A",
            "password": PASSWORD,
        },
    )
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/auth" in cookie


def test_change_password(client):
    session = signup(client, "acme")
    response = client.post(
        "/me/password",
        json={"current_password": PASSWORD, "new_password": "nieuw-lang-wachtwoord"},
        headers=auth(session),
    )
    assert response.status_code == 204
    assert login(client, "eigenaar@acme.nl").status_code == 401
    assert login(client, "eigenaar@acme.nl", "nieuw-lang-wachtwoord").status_code == 200


def test_jwks_verifies_access_token(client):
    session = signup(client, "acme")
    jwk = client.get("/.well-known/jwks.json").json()["keys"][0]
    key = jwt.PyJWK(jwk)
    claims = jwt.decode(
        session["access_token"],
        key.key,
        algorithms=["EdDSA"],
        audience="mywork-hub",
        issuer="http://hub.test",
    )
    assert claims["tslug"] == "acme"
    assert claims["role"] == "owner"


def test_signup_validation(client):
    signup(client, "acme")
    base = {"tenant_name": "X", "display_name": "X", "password": PASSWORD}
    taken = client.post("/signup", json={**base, "slug": "acme", "email": "x@x.nl"})
    assert taken.status_code == 409
    reserved = client.post("/signup", json={**base, "slug": "www", "email": "y@y.nl"})
    assert reserved.status_code == 400
    short_pw = client.post(
        "/signup", json={**base, "slug": "gamma", "email": "z@z.nl", "password": "kort"}
    )
    assert short_pw.status_code == 400


def test_public_tenant(client):
    signup(client, "acme")
    assert client.get("/tenant/public", headers=host("acme")).json()["name"] == "Acme BV"
    assert client.get("/tenant/public?tenant=acme").status_code == 200
    assert client.get("/tenant/public?tenant=onbekend").status_code == 404


def test_tls_ask_only_for_known_tenants(client):
    signup(client, "acme")
    assert client.get("/tls/ask?domain=hub.test").status_code == 200
    assert client.get("/tls/ask?domain=acme.hub.test").status_code == 200
    assert client.get("/tls/ask?domain=onbekend.hub.test").status_code == 404
    assert client.get("/tls/ask?domain=www.hub.test").status_code == 404
    assert client.get("/tls/ask?domain=evil.example.com").status_code == 404


def test_preferences(client):
    session = signup(client, "acme")
    assert session["user"]["preferences"] == {
        "taskbar_position": "bottom",
        "taskbar_autohide": True,
    }
    saved = client.put(
        "/me/preferences",
        json={"taskbar_position": "left", "taskbar_autohide": False},
        headers=auth(session),
    )
    assert saved.status_code == 200
    assert (
        client.get("/me", headers=auth(session)).json()["preferences"]["taskbar_position"] == "left"
    )
    bad = client.put("/me/preferences", json={"taskbar_position": "midden"}, headers=auth(session))
    assert bad.status_code == 422
