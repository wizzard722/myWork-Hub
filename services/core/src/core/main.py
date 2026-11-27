"""Core-service: app-fabriek en opstarten (database, migraties, sleutels)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core import __version__
from core.accounts import AccountError
from core.config import Settings, load_settings
from core.db import Database
from core.migrate import migrate
from core.registry import router as registry_router
from core.routers.audit import router as audit_router
from core.routers.auth import router as auth_router
from core.routers.tenants import router as tenants_router
from core.routers.users import router as users_router
from core.security import TokenSigner
from core.theming import router as theming_router
from mywork_sdk import create_service

log = logging.getLogger("core")


def _configure_audit_logging() -> None:
    """Auditregels als JSON naar stdout (voor een SIEM of logplatform)."""
    audit_log = logging.getLogger("audit")
    if not audit_log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        audit_log.addHandler(handler)
        audit_log.setLevel(logging.INFO)
        audit_log.propagate = False


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    _configure_audit_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.signer = TokenSigner.from_settings(settings)
        app.state.db = None
        if settings.database_url:
            db = Database(settings.database_url)
            await db.wait_until_ready(settings.database_connect_timeout_seconds)
            if settings.auto_migrate:
                await migrate(db.engine)
            app.state.db = db
        else:
            log.warning("HUB_DATABASE_URL niet gezet: core draait zonder database")
        try:
            yield
        finally:
            if app.state.db is not None:
                await app.state.db.close()

    app = create_service(name="core", version=__version__, lifespan=lifespan)
    app.state.settings = settings

    @app.exception_handler(AccountError)
    async def account_error(_: Request, exc: AccountError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(tenants_router)
    app.include_router(theming_router)
    app.include_router(audit_router)
    app.include_router(registry_router)
    return app


app = create_app()
