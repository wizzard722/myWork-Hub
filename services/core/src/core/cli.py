"""Beheeropdrachten voor de core.

    python -m core.cli migrate
    python -m core.cli create-tenant --slug acme --name "Acme BV" \
        --owner-email eigenaar@acme.nl --owner-name "Eigenaar"   (wachtwoord via prompt
        of HUB_OWNER_PASSWORD)
    python -m core.cli generate-key          # Ed25519-sleutel voor HUB_JWT_PRIVATE_KEY

In een container zonder shell: ``docker compose exec core python -m core.cli ...``.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from core.accounts import AccountError, create_tenant
from core.config import load_settings
from core.db import Database
from core.migrate import migrate
from core.security import generate_private_key_pem


async def _with_db(func):
    settings = load_settings()
    if not settings.database_url:
        raise SystemExit("HUB_DATABASE_URL is niet gezet")
    db = Database(settings.database_url)
    try:
        await db.wait_until_ready(settings.database_connect_timeout_seconds)
        await migrate(db.engine)
        return await func(db)
    finally:
        await db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m core.cli", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="databasemigraties uitvoeren")
    sub.add_parser("generate-key", help="nieuwe Ed25519-sleutel (PEM) tonen")
    tenant = sub.add_parser("create-tenant", help="klant met eigenaar aanmaken")
    tenant.add_argument("--slug", required=True, help="subdomein, bijv. acme")
    tenant.add_argument("--name", required=True)
    tenant.add_argument("--owner-email", required=True)
    tenant.add_argument("--owner-name", required=True)
    args = parser.parse_args(argv)

    if args.command == "generate-key":
        print(generate_private_key_pem(), end="")
        return 0
    if args.command == "migrate":
        asyncio.run(_with_db(lambda db: asyncio.sleep(0)))
        print("Database bijgewerkt.")
        return 0

    password = os.environ.get("HUB_OWNER_PASSWORD") or getpass.getpass("Wachtwoord eigenaar: ")

    async def create(db: Database):
        return await create_tenant(
            db,
            slug=args.slug,
            name=args.name,
            owner_email=args.owner_email,
            owner_password=password,
            owner_name=args.owner_name,
        )

    try:
        tenant_obj, owner = asyncio.run(_with_db(create))
    except AccountError as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        return 1
    print(f"Klant '{tenant_obj.slug}' aangemaakt met eigenaar {owner.email}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
