"""Gebruikersbeheer, rollen, thema per klant en Row-Level Security (vereist PostgreSQL)."""

import asyncio
import uuid

import pytest
from core_testkit import PASSWORD, auth, host, signup
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from core.db import Database
from core.models import User


def add_user(client, session, email, role="member", password=PASSWORD):
    return client.post(
        "/users",
        json={
            "email": email,
            "display_name": email.split("@")[0],
            "password": password,
            "role": role,
        },
        headers=auth(session),
    )


def login_as(client, email):
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def test_admin_manages_users(client):
    owner = signup(client, "acme")
    assert add_user(client, owner, "admin@acme.nl", "admin").status_code == 201
    admin = login_as(client, "admin@acme.nl")
    created = add_user(client, admin, "lid@acme.nl")
    assert created.status_code == 201
    users = client.get("/users", headers=auth(admin)).json()
    assert {u["email"] for u in users} == {"eigenaar@acme.nl", "admin@acme.nl", "lid@acme.nl"}

    user_id = created.json()["id"]
    patched = client.patch(f"/users/{user_id}", json={"display_name": "Lid"}, headers=auth(admin))
    assert patched.json()["display_name"] == "Lid"
    assert client.delete(f"/users/{user_id}", headers=auth(admin)).status_code == 204


def test_member_cannot_manage_users(client):
    owner = signup(client, "acme")
    add_user(client, owner, "lid@acme.nl")
    member = login_as(client, "lid@acme.nl")
    assert client.get("/users", headers=auth(member)).status_code == 403
    assert add_user(client, member, "nog1@acme.nl").status_code == 403


def test_admin_cannot_create_or_change_owner(client):
    owner = signup(client, "acme")
    add_user(client, owner, "admin@acme.nl", "admin")
    admin = login_as(client, "admin@acme.nl")
    assert add_user(client, admin, "baas@acme.nl", "owner").status_code == 403
    owner_id = owner["user"]["id"]
    response = client.patch(f"/users/{owner_id}", json={"role": "member"}, headers=auth(admin))
    assert response.status_code == 403


def test_last_owner_is_protected(client):
    owner = signup(client, "acme")
    add_user(client, owner, "tweede@acme.nl", "owner")
    second = login_as(client, "tweede@acme.nl")
    # Eén van twee eigenaren mag weg, de laatste niet.
    owner_id = owner["user"]["id"]
    assert (
        client.patch(f"/users/{owner_id}", json={"role": "admin"}, headers=auth(second)).status_code
        == 200
    )
    users = client.get("/users", headers=auth(second)).json()
    second_id = next(u["id"] for u in users if u["email"] == "tweede@acme.nl")
    # Zichzelf degraderen kan niet, en dan zou er ook geen eigenaar meer zijn.
    response = client.patch(f"/users/{second_id}", json={"role": "admin"}, headers=auth(second))
    assert response.status_code == 409


def test_cannot_delete_self(client):
    owner = signup(client, "acme")
    response = client.delete(f"/users/{owner['user']['id']}", headers=auth(owner))
    assert response.status_code == 409


def test_email_is_unique_across_tenants(client):
    acme = signup(client, "acme")
    signup(client, "beta")
    assert add_user(client, acme, "eigenaar@beta.nl").status_code == 409


def test_deactivated_user_cannot_login(client):
    owner = signup(client, "acme")
    created = add_user(client, owner, "lid@acme.nl").json()
    client.patch(f"/users/{created['id']}", json={"is_active": False}, headers=auth(owner))
    response = client.post("/auth/login", json={"email": "lid@acme.nl", "password": PASSWORD})
    assert response.status_code == 401


def test_cannot_touch_user_of_other_tenant(client):
    acme = signup(client, "acme")
    beta = signup(client, "beta")
    beta_owner_id = beta["user"]["id"]
    response = client.patch(
        f"/users/{beta_owner_id}", json={"display_name": "Gehackt"}, headers=auth(acme)
    )
    assert response.status_code == 404
    assert client.delete(f"/users/{beta_owner_id}", headers=auth(acme)).status_code == 404


# --- Thema per klant -----------------------------------------------------------------


def custom_theme(primary="#ff0000"):
    return {"name": "Acme Portaal", "light": {"primary": primary}}


def test_theme_per_tenant(client):
    acme = signup(client, "acme")
    signup(client, "beta")
    saved = client.put("/theme", json=custom_theme(), headers=auth(acme))
    assert saved.status_code == 200

    acme_css = client.get("/theme/theme.css", headers=host("acme")).text
    beta_css = client.get("/theme/theme.css", headers=host("beta")).text
    assert "--mw-color-primary: #ff0000;" in acme_css
    assert "#ff0000" not in beta_css

    assert client.get("/theme?tenant=acme").json()["name"] == "Acme Portaal"
    # Geen eigen thema: standaardthema met de naam van de klant.
    assert client.get("/theme", headers=host("beta")).json()["name"] == "Beta BV"
    assert client.get("/theme").json()["name"] == "myWork-Hub"


def test_theme_reset(client):
    acme = signup(client, "acme")
    client.put("/theme", json=custom_theme(), headers=auth(acme))
    assert client.delete("/theme", headers=auth(acme)).status_code == 204
    assert client.get("/theme?tenant=acme").json()["name"] == "Acme BV"


def test_theme_requires_admin_and_valid_input(client):
    owner = signup(client, "acme")
    add_user(client, owner, "lid@acme.nl")
    member = login_as(client, "lid@acme.nl")
    assert client.put("/theme", json=custom_theme(), headers=auth(member)).status_code == 403
    bad = client.put("/theme", json=custom_theme("red;}body{"), headers=auth(owner))
    assert bad.status_code == 422
    bad_logo = client.put("/theme", json={"logo_url": "javascript:alert(1)"}, headers=auth(owner))
    assert bad_logo.status_code == 422


def test_tenant_name_owner_only(client):
    owner = signup(client, "acme")
    add_user(client, owner, "admin@acme.nl", "admin")
    admin = login_as(client, "admin@acme.nl")
    assert client.patch("/tenant", json={"name": "Nieuw"}, headers=auth(admin)).status_code == 403
    assert client.patch("/tenant", json={"name": "Nieuw"}, headers=auth(owner)).json()["name"] == (
        "Nieuw"
    )


# --- Row-Level Security rechtstreeks in de database ----------------------------------


def run(coro):
    return asyncio.run(coro)


def test_rls_isolates_tenants(client, database_url):
    acme = signup(client, "acme")
    beta = signup(client, "beta")
    acme_tid = uuid.UUID(client.get("/me", headers=auth(acme)).json()["id"])  # noqa: F841

    async def check():
        db = Database(database_url)
        try:
            async with db.system_session() as session:
                tenants = {u.email: u.tenant_id for u in await session.scalars(select(User))}
            acme_tenant = tenants["eigenaar@acme.nl"]
            beta_tenant = tenants["eigenaar@beta.nl"]

            async with db.tenant_session(acme_tenant) as session:
                emails = {u.email for u in await session.scalars(select(User))}
            assert emails == {"eigenaar@acme.nl"}

            # Schrijven met het tenant_id van een andere klant wordt geweigerd.
            with pytest.raises(DBAPIError):
                async with db.tenant_session(acme_tenant) as session:
                    session.add(
                        User(
                            tenant_id=beta_tenant,
                            email="indringer@acme.nl",
                            password_hash="x",
                            display_name="x",
                            role="member",
                        )
                    )
                    await session.flush()

            # Zonder context (geen klant, geen systeem) is niets zichtbaar.
            async with db._sessions() as session, session.begin():
                await session.execute(text("SET LOCAL ROLE mywork_rls"))
                count = await session.scalar(text("SELECT count(*) FROM users"))
                assert count == 0
        finally:
            await db.close()

    assert beta["tenant"]["slug"] == "beta"
    run(check())


def test_migrations_are_idempotent(database_url):
    from core.migrate import migrate

    async def twice():
        db = Database(database_url)
        try:
            await migrate(db.engine)
            await migrate(db.engine)
        finally:
            await db.close()

    run(twice())


def test_cli_create_tenant(client, database_url, monkeypatch, capsys):
    from core import cli
    from core.config import load_settings

    monkeypatch.setenv("HUB_DATABASE_URL", database_url)
    monkeypatch.setenv("HUB_OWNER_PASSWORD", PASSWORD)
    load_settings.cache_clear()
    try:
        args = ["create-tenant", "--slug", "cli-klant", "--name", "CLI Klant"]
        args += ["--owner-email", "baas@cli.nl", "--owner-name", "Baas"]
        assert cli.main(args) == 0
        assert cli.main(args) == 1  # bestaat al
    finally:
        load_settings.cache_clear()
    assert "aangemaakt" in capsys.readouterr().out
    assert login_as(client, "baas@cli.nl")["tenant"]["slug"] == "cli-klant"
