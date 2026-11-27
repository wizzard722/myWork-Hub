"""Integratietest van de gateway met de echte nginx-configuratie.

Start zonder Docker:
- core, hello en de web-schil (nginx) op eigen loopback-adressen (127.0.0.2/3/4),
- een kleine DNS-server (dnsmasq) die ``core.test``, ``app-hello.test`` en
  ``web.test`` naar die adressen laat wijzen,
- de gateway met ``gateway/nginx.conf`` en een ``env.conf`` met suffix ``.test``.

Zo wordt precies de routering getest die in Docker en Kubernetes draait.
Vereist de programma's ``nginx`` en ``dnsmasq``; anders wordt de test overgeslagen.
"""

import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
NGINX = shutil.which("nginx") or "/usr/sbin/nginx"
DNSMASQ = shutil.which("dnsmasq") or "/usr/sbin/dnsmasq"

pytestmark = pytest.mark.skipif(
    not (os.path.exists(NGINX) and os.path.exists(DNSMASQ)),
    reason="nginx en dnsmasq zijn nodig voor de gateway-test",
)

CORE_IP, HELLO_IP, WEB_IP = "127.0.0.2", "127.0.0.3", "127.0.0.4"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def port_free(host: str, port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex((host, port)) != 0


def wait_for(url: str, procs: list[subprocess.Popen], timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for proc in procs:
            if proc.poll() is not None:
                raise RuntimeError(f"proces {proc.args[0]} stopte met code {proc.returncode}")
        try:
            if httpx.get(url, timeout=0.5).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise TimeoutError(f"{url} kwam niet op")


@pytest.fixture(scope="module")
def gateway(tmp_path_factory) -> Iterator[str]:
    for host, port in ((CORE_IP, 8000), (HELLO_IP, 8000), (WEB_IP, 8080)):
        if not port_free(host, port):
            pytest.skip(f"{host}:{port} is al in gebruik")

    work = tmp_path_factory.mktemp("gateway")
    dist = work / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>web-schil</title>")

    dns_port, gw_port = free_port(), free_port()
    (work / "env.conf").write_text(
        f"resolver 127.0.0.1:{dns_port} valid=1s ipv6=off;\n"
        'map $host $hub_service_suffix { default ".test"; }\n'
    )
    gateway_conf = (
        (ROOT / "gateway" / "nginx.conf")
        .read_text()
        .replace("/tmp/", f"{work}/gw-")
        .replace("/etc/nginx/hub/env.conf", str(work / "env.conf"))
        .replace("listen 8080;", f"listen 127.0.0.1:{gw_port};")
    )
    (work / "gateway.conf").write_text(gateway_conf)
    web_conf = (
        (ROOT / "web" / "nginx.conf")
        .read_text()
        .replace("/tmp/", f"{work}/web-")
        .replace("/usr/share/nginx/html", str(dist))
        .replace("listen 8080;", f"listen {WEB_IP}:8080;")
    )
    if os.geteuid() == 0:
        # Lokaal als root: nginx-workers zouden als "nobody" draaien en de tijdelijke
        # map niet kunnen lezen. In de container draait alles als uid 65532.
        web_conf = "user root;\n" + web_conf
        gateway_conf = "user root;\n" + gateway_conf
        (work / "gateway.conf").write_text(gateway_conf)
    (work / "web.conf").write_text(web_conf)

    env = {**os.environ, "HUB_APPS": f"hello=http://{HELLO_IP}:8000"}
    procs = [
        subprocess.Popen(
            [
                DNSMASQ,
                "--keep-in-foreground",
                "--no-resolv",
                "--no-hosts",
                f"--port={dns_port}",
                "--listen-address=127.0.0.1",
                "--bind-interfaces",
                f"--address=/core.test/{CORE_IP}",
                f"--address=/app-hello.test/{HELLO_IP}",
                f"--address=/web.test/{WEB_IP}",
                f"--pid-file={work}/dnsmasq.pid",
            ],
            stderr=subprocess.DEVNULL,
        ),
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "core.main:app",
                "--host",
                CORE_IP,
                "--port",
                "8000",
                "--root-path",
                "/api/core",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "hello.main:app",
                "--host",
                HELLO_IP,
                "--port",
                "8000",
                "--root-path",
                "/api/apps/hello",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
        subprocess.Popen(
            [NGINX, "-c", str(work / "web.conf"), "-e", "/dev/stderr", "-g", "daemon off;"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
        subprocess.Popen(
            [NGINX, "-c", str(work / "gateway.conf"), "-e", "/dev/stderr", "-g", "daemon off;"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
    ]
    base = f"http://127.0.0.1:{gw_port}"
    try:
        wait_for(f"http://{CORE_IP}:8000/health", procs)
        wait_for(f"http://{HELLO_IP}:8000/health", procs)
        wait_for(f"{base}/healthz", procs)
        yield base
    finally:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            proc.wait(timeout=10)


def test_healthz(gateway):
    assert httpx.get(f"{gateway}/healthz").text == "ok\n"


def test_routes_to_core(gateway):
    assert httpx.get(f"{gateway}/api/core/health").json()["service"] == "core"


def test_routes_to_app_by_id(gateway):
    response = httpx.get(f"{gateway}/api/apps/hello/greetings/Gateway")
    assert response.json() == {"message": "Hallo Gateway, welkom bij myWork-Hub!"}


def test_core_sees_app_through_internal_dns(gateway):
    apps = httpx.get(f"{gateway}/api/core/apps").json()
    assert apps[0]["status"] == "ok"


def test_openapi_uses_public_path(gateway):
    spec = httpx.get(f"{gateway}/api/apps/hello/openapi.json").json()
    assert spec["servers"] == [{"url": "/api/apps/hello"}]


def test_unknown_app_gives_502(gateway):
    assert httpx.get(f"{gateway}/api/apps/bestaat-niet/health").status_code == 502


def test_invalid_app_id_not_routed(gateway):
    assert httpx.get(f"{gateway}/api/apps/Ongeldig_ID/health").status_code == 404


def test_web_shell_and_spa_fallback(gateway):
    for path in ("/", "/een/diepe/route"):
        response = httpx.get(f"{gateway}{path}")
        assert "web-schil" in response.text


def test_security_headers(gateway):
    headers = httpx.get(f"{gateway}/api/core/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-request-id"]
    assert "nginx/" not in headers.get("server", "")
