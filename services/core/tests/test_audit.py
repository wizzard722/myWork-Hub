"""Auditlog: herleidbaarheid, onveranderbaarheid en hash-keten (vereist PostgreSQL)."""

import asyncio

import asyncpg
import pytest
from core_testkit import PASSWORD, auth, signup

INFO = {"X-Real-IP": "203.0.113.7", "X-Request-ID": "req-123", "User-Agent": "pytest-browser"}


def entries(client, session, **params):
    response = client.get("/audit", params=params, headers=auth(session))
    assert response.status_code == 200, response.text
    return response.json()["items"]


def actions(client, session):
    return [e["action"] for e in entries(client, session)]


def add_user(client, session, email, role="member"):
    return client.post(
        "/users",
        json={"email": email, "display_name": "X", "password": PASSWORD, "role": role},
        headers={**auth(session), **INFO},
    )


def test_signup_and_login_are_recorded(client):
    owner = signup(client, "acme")
    client.post(
        "/auth/login", json={"email": "eigenaar@acme.nl", "password": PASSWORD}, headers=INFO
    )
    client.post(
        "/auth/login", json={"email": "eigenaar@acme.nl", "password": "verkeerd"}, headers=INFO
    )
    items = entries(client, owner)
    by_action = {e["action"]: e for e in reversed(items)}
    assert {"tenant.created", "user.created", "auth.login", "auth.login_failed"} <= set(by_action)
    assert by_action["tenant.created"]["actor_type"] == "system"
    failed = by_action["auth.login_failed"]
    assert failed["outcome"] == "denied"
    assert failed["details"]["reason"] == "wachtwoord onjuist"
    assert failed["ip"] == "203.0.113.7"
    assert failed["request_id"] == "req-123"
    assert failed["user_agent"] == "pytest-browser"


def test_admin_actions_are_traceable(client):
    owner = signup(client, "acme")
    created = add_user(client, owner, "lid@acme.nl").json()
    client.patch(f"/users/{created['id']}", json={"role": "admin"}, headers=auth(owner))
    client.patch(f"/users/{created['id']}", json={"is_active": False}, headers=auth(owner))
    client.delete(f"/users/{created['id']}", headers=auth(owner))
    client.put("/theme", json={"name": "Nieuw"}, headers=auth(owner))

    items = entries(client, owner)
    actions_seen = [e["action"] for e in items]
    for action in (
        "user.created",
        "user.role_changed",
        "user.deactivated",
        "user.deleted",
        "theme.updated",
    ):
        assert action in actions_seen, action
    role_change = next(e for e in items if e["action"] == "user.role_changed")
    assert role_change["actor_email"] == "eigenaar@acme.nl"
    assert role_change["actor_role"] == "owner"
    assert role_change["target_id"] == created["id"]
    assert role_change["details"]["changes"]["role"] == ["member", "admin"]


def test_denied_actions_are_recorded(client):
    owner = signup(client, "acme")
    add_user(client, owner, "admin@acme.nl", "admin")
    add_user(client, owner, "lid@acme.nl")
    admin = client.post("/auth/login", json={"email": "admin@acme.nl", "password": PASSWORD}).json()
    member = client.post("/auth/login", json={"email": "lid@acme.nl", "password": PASSWORD}).json()

    assert add_user(client, admin, "baas@acme.nl", "owner").status_code == 403
    assert client.get("/users", headers=auth(member)).status_code == 403
    owner_id = owner["user"]["id"]
    assert client.delete(f"/users/{owner_id}", headers=auth(owner)).status_code == 409

    denied = entries(client, owner, outcome="denied")
    reasons = {(e["action"], e["actor_email"]) for e in denied}
    assert ("user.created", "admin@acme.nl") in reasons
    assert ("admin.get /users", "lid@acme.nl") in reasons
    assert ("user.deleted", "eigenaar@acme.nl") in reasons


def test_member_cannot_read_audit_log(client):
    owner = signup(client, "acme")
    add_user(client, owner, "lid@acme.nl")
    member = client.post("/auth/login", json={"email": "lid@acme.nl", "password": PASSWORD}).json()
    assert client.get("/audit", headers=auth(member)).status_code == 403


def test_tenants_only_see_their_own_audit_log(client):
    acme = signup(client, "acme")
    beta = signup(client, "beta")
    acme_ids = {e["id"] for e in entries(client, acme)}
    beta_ids = {e["id"] for e in entries(client, beta)}
    assert acme_ids and beta_ids and not acme_ids & beta_ids
    assert all(e["actor_email"] != "eigenaar@beta.nl" for e in entries(client, acme))


def test_filters_and_paging(client):
    owner = signup(client, "acme")
    for i in range(3):
        add_user(client, owner, f"lid{i}@acme.nl")
    users = entries(client, owner, action="user.created")
    assert len(users) == 4  # eigenaar + 3
    page = client.get("/audit", params={"limit": 2}, headers=auth(owner)).json()
    assert len(page["items"]) == 2 and page["next_before_id"]
    rest = client.get(
        "/audit", params={"limit": 50, "before_id": page["next_before_id"]}, headers=auth(owner)
    ).json()
    assert {e["id"] for e in rest["items"]}.isdisjoint({e["id"] for e in page["items"]})


def test_export_csv_is_itself_recorded(client):
    owner = signup(client, "acme")
    response = client.get("/audit/export.csv", headers=auth(owner))
    assert response.headers["content-type"].startswith("text/csv")
    assert "tenant.created" in response.text
    assert "audit.exported" in actions(client, owner)


def test_assistant_events(client):
    owner = signup(client, "acme")
    response = client.post(
        "/audit/events",
        json={"action": "assistant.tool_call", "target_type": "app", "target_id": "hello"},
        headers=auth(owner),
    )
    assert response.status_code == 201
    event = entries(client, owner, action="assistant.")[0]
    assert event["actor_type"] == "assistant"
    assert event["actor_email"] == "eigenaar@acme.nl"
    bad = client.post("/audit/events", json={"action": "user.deleted"}, headers=auth(owner))
    assert bad.status_code == 422


# --- Onveranderbaarheid en hash-keten ------------------------------------------------


def run_sql(database_url: str, *statements: str):
    async def go():
        conn = await asyncpg.connect(database_url.replace("postgresql+asyncpg://", "postgresql://"))
        try:
            results = []
            for statement in statements:
                results.append(await conn.execute(statement))
            return results
        finally:
            await conn.close()

    return asyncio.run(go())


def test_chain_verifies(client):
    owner = signup(client, "acme")
    add_user(client, owner, "lid@acme.nl")
    result = client.get("/audit/verify", headers=auth(owner)).json()
    assert result["valid"] is True and result["checked"] >= 3


@pytest.mark.parametrize(
    "statement",
    ["UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log"],
)
def test_audit_log_cannot_be_changed_even_by_superuser(client, database_url, statement):
    signup(client, "acme")
    with pytest.raises(asyncpg.RaiseError, match="onveranderbaar"):
        run_sql(database_url, statement)


def test_application_role_has_no_update_rights(client, database_url):
    signup(client, "acme")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        run_sql(
            database_url,
            "BEGIN",
            "SET LOCAL ROLE mywork_rls",
            "SELECT set_config('app.system', 'on', true)",
            "UPDATE audit_log SET action = 'x'",
        )


def test_tampering_is_detected(client, database_url):
    owner = signup(client, "acme")
    add_user(client, owner, "lid@acme.nl")
    # Een aanvaller met volledige databasetoegang zet de trigger uit en wijzigt een regel.
    run_sql(
        database_url,
        "ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_update_delete",
        'UPDATE audit_log SET details = \'{"email": "iemand-anders@acme.nl"}\' '
        "WHERE action = 'user.created' AND details->>'email' = 'lid@acme.nl'",
        "ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_update_delete",
    )
    result = client.get("/audit/verify", headers=auth(owner)).json()
    assert result["valid"] is False
    assert result["first_invalid_id"] is not None
