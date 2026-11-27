"""Auditlog: onveranderbaar, met hash-keten per klant.

Revision ID: 0002
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

FILTER = (
    "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.system', true) = 'on'"
)

STATEMENTS = [
    # Geen foreign key naar tenants: de geschiedenis blijft bestaan, ook als een klant
    # wordt verwijderd. tenant_id NULL = platformgebeurtenis (bijv. onbekend e-mailadres).
    """
    CREATE TABLE audit_log (
        id bigserial PRIMARY KEY,
        tenant_id uuid,
        occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        actor_type text NOT NULL CHECK (actor_type IN ('user', 'assistant', 'system')),
        actor_id uuid,
        actor_email text,
        actor_role text,
        action text NOT NULL,
        outcome text NOT NULL CHECK (outcome IN ('success', 'denied', 'failure')),
        target_type text,
        target_id text,
        details jsonb NOT NULL DEFAULT '{}'::jsonb,
        ip text,
        user_agent text,
        request_id text,
        prev_hash text,
        hash text NOT NULL
    )
    """,
    "CREATE INDEX audit_log_tenant_idx ON audit_log (tenant_id, id DESC)",
    "CREATE INDEX audit_log_action_idx ON audit_log (tenant_id, action)",
    # Alleen toevoegen en lezen: geen UPDATE/DELETE voor de applicatierol...
    "GRANT SELECT, INSERT ON audit_log TO mywork_rls",
    "GRANT USAGE ON SEQUENCE audit_log_id_seq TO mywork_rls",
    # ...en een trigger die wijzigen en verwijderen voor iedereen blokkeert.
    """
    CREATE FUNCTION audit_log_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'audit_log is onveranderbaar (% niet toegestaan)', TG_OP;
    END
    $$
    """,
    """
    CREATE TRIGGER audit_log_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_immutable()
    """,
    "ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE audit_log FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY audit_read ON audit_log FOR SELECT USING ({FILTER})",
    f"CREATE POLICY audit_insert ON audit_log FOR INSERT WITH CHECK ({FILTER})",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE audit_log")
    op.execute("DROP FUNCTION audit_log_immutable()")
