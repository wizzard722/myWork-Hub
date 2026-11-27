"""Integratietest: core en een app draaien als echte, losse processen.

Start core en hello met uvicorn op vrije poorten (zonder Docker) en controleert dat
ze via HTTP met elkaar praten, zoals ze dat in Docker en Kubernetes doen.
"""

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_until_up(url: str, process: subprocess.Popen, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{url} is gestopt met code {process.returncode}")
        try:
            if httpx.get(f"{url}/health", timeout=0.5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise TimeoutError(f"{url} kwam niet op binnen {timeout}s")


def start(module: str, port: int, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", f"{module}:app", "--port", str(port)],
        cwd=ROOT,
        env={**os.environ, **env},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@pytest.fixture(scope="module")
def stack() -> Iterator[dict[str, str]]:
    hello_port, core_port, missing_port = free_port(), free_port(), free_port()
    hello_url = f"http://127.0.0.1:{hello_port}"
    core_url = f"http://127.0.0.1:{core_port}"
    processes = [
        start("hello.main", hello_port, {}),
        start(
            "core.main",
            core_port,
            {"HUB_APPS": f"hello={hello_url},ontbreekt=http://127.0.0.1:{missing_port}"},
        ),
    ]
    try:
        wait_until_up(hello_url, processes[0])
        wait_until_up(core_url, processes[1])
        yield {"core": core_url, "hello": hello_url}
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            process.wait(timeout=10)


def test_core_discovers_running_app(stack):
    apps = {a["id"]: a for a in httpx.get(f"{stack['core']}/apps").json()}
    assert apps["hello"]["status"] == "ok"
    assert apps["hello"]["manifest"]["publishes"][0]["name"] == "hello.greeted"


def test_core_reports_missing_app(stack):
    apps = {a["id"]: a for a in httpx.get(f"{stack['core']}/apps").json()}
    assert apps["ontbreekt"]["status"] == "unreachable"


def test_app_api_reachable(stack):
    response = httpx.get(f"{stack['hello']}/greetings/Test")
    assert response.json() == {"message": "Hallo Test, welkom bij myWork-Hub!"}


def test_theme_served_as_css(stack):
    response = httpx.get(f"{stack['core']}/theme/theme.css")
    assert response.headers["content-type"].startswith("text/css")
    assert "--mw-color-primary" in response.text
