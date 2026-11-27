"""Klanten, gebruikers, refresh-tokens en thema's, met Row-Level Security.

Revision ID: 0001
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = ["users", "refresh_tokens", "tenant_themes"]
SLUG_CHECK = r"slug ~ '^[a-z][a-z0-9-]{1,38}[a-z0-9]$'"

# Zichtbaar: rijen van de klant uit app.tenant_id, of alles in systeemcontext.
TENANT_FILTER = (
    "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.system', true) = 'on'"
)

# asyncpg voert één statement per aanroep uit: daarom een lijst.
STATEMENTS = [
    f"""
    CREATE TABLE tenants (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        slug text NOT NULL UNIQUE CHECK ({SLUG_CHECK}),
        name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
        status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE users (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        email text NOT NULL CHECK (email = lower(email)),
        password_hash text NOT NULL,
        display_name text NOT NULL CHECK (length(display_name) BETWEEN 1 AND 120),
        role text NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
        is_active boolean NOT NULL DEFAULT true,
        created_at timestamptz NOT NULL DEFAULT now(),
        last_login_at timestamptz
    )
    """,
    # Eén account hoort bij precies één klant: e-mail is uniek over de hele hub.
    "CREATE UNIQUE INDEX users_email_key ON users (email)",
    "CREATE INDEX users_tenant_idx ON users (tenant_id)",
    """
    CREATE TABLE refresh_tokens (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash text NOT NULL UNIQUE,
        family_id uuid NOT NULL,
        expires_at timestamptz NOT NULL,
        revoked_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX refresh_tokens_family_idx ON refresh_tokens (family_id)",
    "CREATE INDEX refresh_tokens_user_idx ON refresh_tokens (user_id)",
    """
    CREATE TABLE tenant_themes (
        tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
        theme jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    # Rol waaronder alle queries draaien, zodat RLS ook geldt voor eigenaar/superuser.
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mywork_rls') THEN
            CREATE ROLE mywork_rls NOLOGIN;
        END IF;
    END
    $$
    """,
    "GRANT mywork_rls TO CURRENT_USER",
    "GRANT USAGE ON SCHEMA public TO mywork_rls",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON tenants, users, refresh_tokens, tenant_themes "
    "TO mywork_rls",
    "ALTER TABLE tenants ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE tenants FORCE ROW LEVEL SECURITY",
    # Klanten zelf: alleen de eigen klant zichtbaar; aanmaken/wijzigen alleen als systeem.
    """
    CREATE POLICY tenant_isolation ON tenants
        USING (id = nullif(current_setting('app.tenant_id', true), '')::uuid
               OR current_setting('app.system', true) = 'on')
        WITH CHECK (current_setting('app.system', true) = 'on')
    """,
]
for _table in TENANT_TABLES:
    STATEMENTS += [
        f"ALTER TABLE {_table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {_table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY tenant_isolation ON {_table} "
        f"USING ({TENANT_FILTER}) WITH CHECK ({TENANT_FILTER})",
    ]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE tenant_themes, refresh_tokens, users, tenants CASCADE")
