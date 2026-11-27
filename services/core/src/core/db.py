"""Databasetoegang met afscherming per klant (PostgreSQL Row-Level Security).

Elke transactie draait als de rol ``mywork_rls`` (geen eigenaar, geen superuser), zodat
de RLS-policies altijd gelden — ook als de verbinding zelf als eigenaar of superuser
inlogt. Daarnaast zet elke transactie één van twee contexten:

- ``tenant_session(tenant_id)``: alleen rijen van die klant zijn zichtbaar en
  schrijfbaar (``app.tenant_id``).
- ``system_session()``: klantoverstijgend (``app.system = on``), alleen voor inloggen,
  aanmelden en beheer-CLI. Gebruik dit bewust en zo kort mogelijk.

Een query zonder context ziet niets: vergeten te filteren lekt dus geen data.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

log = logging.getLogger(__name__)

RLS_ROLE = "mywork_rls"


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True)
        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def wait_until_ready(self, timeout: float) -> None:
        """Wacht tot de database bereikbaar is (bijv. bij gelijktijdig starten)."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            try:
                async with self.engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                return
            except Exception:
                if asyncio.get_running_loop().time() >= deadline:
                    raise
                log.info("Database nog niet bereikbaar, opnieuw proberen...")
                await asyncio.sleep(1)

    @asynccontextmanager
    async def _session(self, settings: dict[str, str]) -> AsyncIterator[AsyncSession]:
        async with self._sessions() as session, session.begin():
            await session.execute(text(f"SET LOCAL ROLE {RLS_ROLE}"))
            for key, value in settings.items():
                await session.execute(
                    text("SELECT set_config(:key, :value, true)"), {"key": key, "value": value}
                )
            yield session

    def tenant_session(self, tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
        return self._session({"app.tenant_id": str(tenant_id)})

    def system_session(self) -> AsyncIterator[AsyncSession]:
        return self._session({"app.system": "on"})

    async def close(self) -> None:
        await self.engine.dispose()
