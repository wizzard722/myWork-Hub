import httpx
import pytest

from core.config import Settings
from core.registry import probe_app

MANIFEST = {"id": "hello", "name": "Hello", "version": "0.1.0"}


def make_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_app_urls_parsing():
    settings = Settings(apps=" hello=http://app-hello:8000/ , files=http://files:8000")
    assert settings.app_urls() == {"hello": "http://app-hello:8000", "files": "http://files:8000"}


def test_app_urls_invalid():
    with pytest.raises(ValueError):
        Settings(apps="hello").app_urls()


async def _probe(handler, app_id="hello"):
    async with make_client(handler) as client:
        return await probe_app(client, app_id, "http://app")


def run(coro):
    import asyncio

    return asyncio.run(coro)


def test_probe_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, json=MANIFEST)

    result = run(_probe(handler))
    assert result.status == "ok"
    assert result.manifest.name == "Hello"


def test_probe_unreachable():
    def handler(request):
        raise httpx.ConnectError("down")

    assert run(_probe(handler)).status == "unreachable"


def test_probe_id_mismatch():
    result = run(_probe(lambda r: httpx.Response(200, json=MANIFEST), app_id="other"))
    assert result.status == "invalid"


def test_probe_bad_manifest():
    result = run(_probe(lambda r: httpx.Response(200, json={"id": "hello"})))
    assert result.status == "invalid"
