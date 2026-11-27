"""Testinfrastructuur voor de core: een tijdelijke PostgreSQL-database.

Gebruikt ``HUB_TEST_DATABASE_URL`` als die gezet is (PostgreSQL-superuser, bijv.
``postgresql+asyncpg://postgres:pw@localhost:5432/postgres``). Anders wordt met de
PostgreSQL-programma's (``initdb``/``pg_ctl``) een tijdelijk cluster gestart. Zijn die er
niet, dan worden de databasetests overgeslagen.
"""

from __future__ import annotations

import asyncio
import glob
import os
import shutil
import socket
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import asyncpg
import pytest
from fastapi.testclient import TestClient

from core.config import Settings
from core.main import create_app

BASE_DOMAIN = "hub.test"
TEST_DB = "mywork_test"


def _pg_bin() -> Path | None:
    for candidate in sorted(glob.glob("/usr/lib/postgresql/*/bin"), reverse=True):
        if Path(candidate, "pg_ctl").exists():
            return Path(candidate)
    found = shutil.which("pg_ctl")
    return Path(found).parent if found else None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run(cmd: list[str], as_postgres: bool) -> None:
    if as_postgres:
        cmd = ["runuser", "-u", "postgres", "--", *cmd]
    subprocess.run(cmd, check=True, capture_output=True)


@pytest.fixture(scope="session")
def admin_dsn() -> Iterator[str]:
    """DSN (asyncpg-vorm) van een superuser-verbinding."""
    if url := os.environ.get("HUB_TEST_DATABASE_URL"):
        yield url.replace("postgresql+asyncpg://", "postgresql://")
        return
    pg_bin = _pg_bin()
    if pg_bin is None:
        pytest.skip("PostgreSQL niet gevonden (zet HUB_TEST_DATABASE_URL of installeer postgresql)")
    as_postgres = os.geteuid() == 0  # initdb weigert als root te draaien
    workdir = Path(tempfile.mkdtemp(prefix="mywork-pg-"))
    data, sockets = workdir / "data", workdir / "sock"
    sockets.mkdir()
    if as_postgres:
        shutil.chown(workdir, "postgres")
        shutil.chown(sockets, "postgres")
    port = _free_port()
    _run([str(pg_bin / "initdb"), "-D", str(data), "-U", "postgres", "-A", "trust"], as_postgres)
    _run(
        [
            str(pg_bin / "pg_ctl"), "-D", str(data), "-w", "-l", str(workdir / "log"),
            "-o", f"-p {port} -k {sockets} -c listen_addresses=127.0.0.1 -c fsync=off",
            "start",
        ],
        as_postgres,
    )  # fmt: skip
    try:
        yield f"postgresql://postgres@127.0.0.1:{port}/postgres"
    finally:
        _run([str(pg_bin / "pg_ctl"), "-D", str(data), "-m", "immediate", "stop"], as_postgres)
        shutil.rmtree(workdir, ignore_errors=True)


async def _execute(dsn: str, *statements: str) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        for statement in statements:
            await conn.execute(statement)
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def database_url(admin_dsn: str) -> str:
    asyncio.run(
        _execute(admin_dsn, f"DROP DATABASE IF EXISTS {TEST_DB}", f"CREATE DATABASE {TEST_DB}")
    )
    base = admin_dsn.rsplit("/", 1)[0]
    return f"{base.replace('postgresql://', 'postgresql+asyncpg://')}/{TEST_DB}"


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        base_domain=BASE_DOMAIN,
        public_url=f"http://{BASE_DOMAIN}",
        cookie_secure=False,
        allow_signup=True,
        apps="",
    )


@pytest.fixture
def client(settings: Settings, database_url: str) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app, base_url=f"http://{BASE_DOMAIN}") as test_client:
        dsn = database_url.replace("postgresql+asyncpg://", "postgresql://")
        asyncio.run(_execute(dsn, "TRUNCATE tenants, audit_log CASCADE"))
        yield test_client
