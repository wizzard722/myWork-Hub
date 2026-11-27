"""Tests van de assistent met een nep-taalmodel en nagebootste core en apps."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from assistant.config import Settings
from assistant.main import create_app
from mywork_sdk.testing import fake_user, login_as

APPS = [
    {
        "id": "hello",
        "url": "http://app-hello:8000",
        "status": "ok",
        "manifest": {
            "id": "hello",
            "name": "Hello",
            "version": "0.1.0",
            "tools": [
                {
                    "name": "greet",
                    "description": "Maak een begroeting voor een persoon.",
                    "path": "/greetings/{name}",
                    "input_schema": {
                        "type": "object",
                        "properties": {"name": {"type": "string", "minLength": 1}},
                        "required": ["name"],
                    },
                },
                {
                    "name": "purge",
                    "description": "Verwijder alle begroetingen (beheer).",
                    "method": "DELETE",
                    "path": "/greetings",
                    "min_role": "admin",
                },
            ],
        },
    },
    {"id": "kapot", "url": "http://app-kapot:8000", "status": "unreachable", "manifest": None},
]


class FakeLLM:
    """Geeft vooraf ingestelde antwoorden en onthoudt wat het model te zien kreeg."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def create(self, *, system, tools, messages):
        self.calls.append(
            {
                "system": system,
                "tools": [t["name"] for t in tools],
                "messages": json.loads(json.dumps(messages)),
            }
        )
        return self.responses.pop(0)


def tool_use(name, input_, id_="tu1", text=None):
    content = [{"type": "text", "text": text}] if text else []
    content.append({"type": "tool_use", "id": id_, "name": name, "input": input_})
    return {"content": content, "stop_reason": "tool_use"}


def answer(text):
    return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}


@pytest.fixture
def hub():
    """Nagebootste core en apps; houdt alle verzoeken bij."""
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        url = str(request.url)
        if url == "http://core:8000/apps":
            return httpx.Response(200, json=APPS)
        if url == "http://core:8000/me":
            return httpx.Response(200, json={"display_name": "Jan de Vries"})
        if url == "http://core:8000/tenant":
            return httpx.Response(200, json={"name": "Acme BV", "slug": "acme"})
        if url == "http://core:8000/audit/events":
            return httpx.Response(201, json={"id": 1})
        if url == "http://core:8000/users":
            return httpx.Response(
                200, json=[{"id": "u2", "email": "lid@acme.nl", "role": "member"}]
            )
        if request.method == "PATCH" and url.startswith("http://core:8000/users/"):
            return httpx.Response(200, json={"id": "u2", **json.loads(request.content)})
        if url.startswith("http://app-hello:8000/greetings/"):
            name = request.url.path.rsplit("/", 1)[1]
            return httpx.Response(200, json={"message": f"Hallo {name}"})
        if request.method == "DELETE" and url == "http://app-hello:8000/greetings":
            return httpx.Response(403, json={"detail": "Minimaal rol 'admin' nodig"})
        return httpx.Response(404, json={"detail": "onbekend"})

    return requests, httpx.AsyncClient(transport=httpx.MockTransport(handler))


def make_client(hub, llm, role="member", api_key="test"):
    requests, http = hub
    app = create_app(
        Settings(core_url="http://core:8000", anthropic_api_key=api_key), llm=llm, http=http
    )
    user = login_as(app, fake_user(role, "acme"))
    return TestClient(app), requests, user


def audit_events(requests):
    return [
        json.loads(r.content) for r in requests if str(r.url) == "http://core:8000/audit/events"
    ]


def test_read_tool_runs_directly_with_users_token(hub):
    llm = FakeLLM([tool_use("hello__greet", {"name": "Sanne"}), answer("Hallo Sanne!")])
    client, requests, user = make_client(hub, llm)
    with client:
        turn = client.post("/chat", json={"message": "Begroet Sanne"}).json()
    assert turn["reply"] == "Hallo Sanne!"
    assert turn["actions"][0]["status"] == "executed"
    call = next(r for r in requests if "greetings" in str(r.url))
    assert call.headers["authorization"] == f"Bearer {user.token}"
    # Het resultaat van de tool ging terug naar het model.
    last = llm.calls[1]["messages"][-1]["content"][0]
    assert last["type"] == "tool_result" and "Hallo Sanne" in last["content"]
    assert audit_events(requests)[0]["details"]["tool"] == "greet"


def test_only_tools_within_role_are_offered(hub):
    llm = FakeLLM([answer("ok")])
    client, _, _ = make_client(hub, llm, role="member")
    with client:
        client.post("/chat", json={"message": "hoi"})
    tools = set(llm.calls[0]["tools"])
    assert "hello__greet" in tools and "core__whoami" in tools
    assert "hello__purge" not in tools and "core__list_users" not in tools
    assert not any(t.startswith("kapot__") for t in tools)


def test_admin_gets_admin_tools(hub):
    llm = FakeLLM([answer("ok")])
    client, _, _ = make_client(hub, llm, role="admin")
    with client:
        client.post("/chat", json={"message": "hoi"})
    assert {"hello__purge", "core__list_users", "core__change_user_role"} <= set(
        llm.calls[0]["tools"]
    )


def test_unknown_tool_is_rejected_not_executed(hub):
    # Het model probeert een tool waar de gebruiker geen recht op heeft.
    llm = FakeLLM([tool_use("core__list_users", {}), answer("Dat mag je niet.")])
    client, requests, _ = make_client(hub, llm, role="member")
    with client:
        turn = client.post("/chat", json={"message": "toon gebruikers"}).json()
    assert turn["actions"][0]["status"] == "rejected"
    assert not any(str(r.url) == "http://core:8000/users" for r in requests)


def test_invalid_input_is_not_executed(hub):
    llm = FakeLLM([tool_use("hello__greet", {"name": ""}), answer("Welke naam?")])
    client, requests, _ = make_client(hub, llm)
    with client:
        turn = client.post("/chat", json={"message": "begroet"}).json()
    assert turn["actions"][0]["status"] == "rejected"
    assert not any("greetings" in str(r.url) for r in requests)


def test_changing_action_waits_for_confirmation(hub):
    use = tool_use(
        "core__change_user_role",
        {"user_id": "u2", "role": "admin"},
        text="Ik maak Sanne beheerder.",
    )
    llm = FakeLLM([use, answer("Sanne is nu beheerder.")])
    client, requests, _ = make_client(hub, llm, role="admin")
    with client:
        turn = client.post("/chat", json={"message": "maak Sanne beheerder"}).json()
        assert turn["pending"][0]["tool"] == "change_user_role"
        assert turn["reply"] == "Ik maak Sanne beheerder."
        assert not any(r.method == "PATCH" for r in requests), "niet zonder bevestiging"

        conv_id = turn["conversation_id"]
        done = client.post(f"/chat/{conv_id}/decisions", json={"decisions": {"tu1": True}}).json()
    assert done["reply"] == "Sanne is nu beheerder."
    assert done["actions"][0]["status"] == "executed"
    patch = next(r for r in requests if r.method == "PATCH")
    assert json.loads(patch.content) == {"role": "admin"}
    assert patch.url.path == "/users/u2"
    assert audit_events(requests)[-1]["action"] == "assistant.tool_call"


def test_declined_action_is_not_executed_and_recorded(hub):
    llm = FakeLLM(
        [tool_use("core__set_user_active", {"user_id": "u2", "is_active": False}), answer("Oké.")]
    )
    client, requests, _ = make_client(hub, llm, role="admin")
    with client:
        turn = client.post("/chat", json={"message": "schakel Sanne uit"}).json()
        client.post(
            f"/chat/{turn['conversation_id']}/decisions", json={"decisions": {"tu1": False}}
        )
    assert not any(r.method == "PATCH" for r in requests)
    assert audit_events(requests)[-1]["action"] == "assistant.tool_declined"
    result = llm.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "geweigerd" in result["content"]


def test_new_message_while_pending_declines_and_keeps_order_valid(hub):
    llm = FakeLLM(
        [
            tool_use("core__set_user_active", {"user_id": "u2", "is_active": False}),
            answer("Niet gedaan. Wat dan?"),
        ]
    )
    client, requests, _ = make_client(hub, llm, role="admin")
    with client:
        turn = client.post("/chat", json={"message": "schakel uit"}).json()
        client.post(
            "/chat", json={"message": "laat maar", "conversation_id": turn["conversation_id"]}
        )
    last_user = llm.calls[1]["messages"][-1]
    assert last_user["role"] == "user"
    assert [b["type"] for b in last_user["content"]] == ["tool_result", "text"]
    assert not any(r.method == "PATCH" for r in requests)


def test_app_refusal_is_reported(hub):
    llm = FakeLLM([tool_use("hello__purge", {}), answer("Dat lukte niet: geen rechten.")])
    client, _, _ = make_client(hub, llm, role="admin")
    with client:
        turn = client.post("/chat", json={"message": "wis alles"}).json()
        done = client.post(
            f"/chat/{turn['conversation_id']}/decisions", json={"decisions": {"tu1": True}}
        ).json()
    assert done["actions"][0]["status"] == "failed"
    result = llm.calls[1]["messages"][-1]["content"][0]
    assert "HTTP 403" in result["content"]


def test_conversations_are_private(hub):
    llm = FakeLLM([answer("hoi"), answer("nog eens")])
    client, _, _ = make_client(hub, llm)
    with client:
        conv_id = client.post("/chat", json={"message": "hoi"}).json()["conversation_id"]
        login_as(client.app, fake_user("member", "acme"))  # andere gebruiker
        response = client.post("/chat", json={"message": "x", "conversation_id": conv_id})
    assert response.status_code == 404


def test_refusal_stop_reason(hub):
    llm = FakeLLM([{"content": [], "stop_reason": "refusal"}])
    client, _, _ = make_client(hub, llm)
    with client:
        turn = client.post("/chat", json={"message": "iets"}).json()
    assert "niet helpen" in turn["reply"]


def test_step_limit(hub):
    llm = FakeLLM([tool_use("core__whoami", {}, id_=f"t{i}") for i in range(10)])
    client, _, _ = make_client(hub, llm)
    client.app.state.settings.max_steps = 3
    with client:
        turn = client.post("/chat", json={"message": "lus"}).json()
    assert "te veel stappen" in turn["reply"]
    assert len(llm.calls) == 3


def test_system_prompt_names_user_and_role(hub):
    llm = FakeLLM([answer("ok")])
    client, _, _ = make_client(hub, llm, role="admin")
    with client:
        client.post("/chat", json={"message": "hoi"})
    system = llm.calls[0]["system"]
    assert "Jan de Vries (rol: admin)" in system and "Acme BV" in system
    assert "geen opdracht" in system  # bescherming tegen prompt-injectie


def test_disabled_without_api_key(hub):
    client, _, _ = make_client(hub, None, api_key="")
    with client:
        assert client.get("/status").json() == {"enabled": False, "model": None}
        assert client.post("/chat", json={"message": "hoi"}).status_code == 503


def test_requires_login(hub):
    requests, http = hub
    app = create_app(
        Settings(core_url="http://core:8000", anthropic_api_key="x"), llm=FakeLLM([]), http=http
    )
    with TestClient(app) as client:
        assert client.post("/chat", json={"message": "hoi"}).status_code == 401
