"""De koppeling met de Anthropic API: wat wordt er verstuurd en hoe wordt het gelezen.

Geen echte API-aanroep: de HTTP-laag van de SDK wordt nagebootst.
"""

import json

import anthropic
import httpx2 as httpx
import pytest

from assistant.llm import AnthropicLLM, LLMError


def llm_with(handler):
    http = anthropic.DefaultAsyncHttpxClient(transport=httpx.MockTransport(handler))
    return AnthropicLLM("sk-test", "claude-opus-5-5", "medium", 16000, http_client=http)


MESSAGE = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-opus-5-5",
    "content": [
        {"type": "text", "text": "Ik zoek het op."},
        {"type": "tool_use", "id": "toolu_1", "name": "hello__greet", "input": {"name": "Sanne"}},
    ],
    "stop_reason": "tool_use",
    "stop_sequence": None,
    "usage": {"input_tokens": 10, "output_tokens": 5},
}


@pytest.mark.anyio
async def test_request_and_response():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["headers"] = request.headers
        return httpx.Response(200, json=MESSAGE)

    result = await llm_with(handler).create(
        system="sys", tools=[{"name": "t", "input_schema": {"type": "object"}}], messages=[]
    )
    body = seen["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["output_config"] == {"effort": "medium"}
    assert body["fallbacks"] == "default"
    assert body["cache_control"] == {"type": "ephemeral"}
    assert "server-side-fallback-2026-07-01" in seen["headers"]["anthropic-beta"]
    assert result["stop_reason"] == "tool_use"
    assert result["content"][1] == {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "hello__greet",
        "input": {"name": "Sanne"},
    }


@pytest.mark.anyio
async def test_rate_limit_becomes_friendly_error():
    def handler(request):
        return httpx.Response(
            429,
            json={"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}},
            headers={"retry-after": "0"},
        )

    llm = llm_with(handler)
    llm.client = llm.client.with_options(max_retries=0)
    with pytest.raises(LLMError) as exc:
        await llm.create(system="s", tools=[], messages=[])
    assert exc.value.status_code == 429


@pytest.fixture
def anyio_backend():
    return "asyncio"
