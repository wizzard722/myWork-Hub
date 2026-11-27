"""Alembic-omgeving. Wordt aangeroepen vanuit core.migrate met een open verbinding."""

from alembic import context

import core.audit  # noqa: F401  (registreert AuditEntry)
from core.models import Base

connection = context.config.attributes["connection"]
context.configure(connection=connection, target_metadata=Base.metadata)
with context.begin_transaction():
    context.run_migrations()
