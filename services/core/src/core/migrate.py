"""Databasemigraties (Alembic), veilig bij meerdere gelijktijdig startende replica's."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

MIGRATIONS = Path(__file__).parent / "migrations"
# Vaste sleutel voor pg_advisory_lock: maar één replica migreert tegelijk.
LOCK_KEY = 7_221_964_001


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    return config


def _upgrade(connection) -> None:
    config = alembic_config()
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


async def migrate(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": LOCK_KEY})
        await conn.commit()
        try:
            await conn.run_sync(_upgrade)
            await conn.commit()
        except BaseException:
            await conn.rollback()
            raise
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
            await conn.commit()
