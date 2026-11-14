"""Non-superuser application role ``metis_app``.

Superusers bypass RLS, so the api and workers connect as ``metis_app``
(``NOSUPERUSER NOBYPASSRLS``) while migrations keep the owner role. The role
gets DML on every table in ``core`` and ``identity`` and, through default
privileges, on tables later migrations create there. A migration that adds a
new schema must grant ``metis_app`` on it the same way.

Login: when ``APP_DB_PASSWORD`` is set while migrating (compose sets it), the
role gets ``LOGIN`` with that password. Without it the role stays ``NOLOGIN``
and is only usable via ``SET ROLE`` (tests). To change the password later, run
``ALTER ROLE metis_app PASSWORD '...'`` by hand; this migration runs once.
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0004_app_role"
down_revision = "0003_identity"
branch_labels = None
depends_on = None

APP_ROLE = "metis_app"
APP_SCHEMAS = ("core", "identity")
PASSWORD_ENV = "APP_DB_PASSWORD"
_TABLE_PRIVILEGES = "SELECT, INSERT, UPDATE, DELETE"

_CREATE_ROLE = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
        CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    END IF;
END
$$
"""


def _on_database(statement: str) -> str:
    """Run ``statement`` with ``%I`` bound to the current database name."""
    return f"DO $$ BEGIN EXECUTE format('{statement}', current_database()); END $$"


def _enable_login(password: str) -> None:
    # ALTER ROLE takes no bind parameters; quote the literal server-side with %L.
    quote = f"SELECT format('ALTER ROLE {APP_ROLE} LOGIN PASSWORD %L', CAST(:password AS text))"
    statement = op.get_bind().scalar(sa.text(quote), {"password": password})
    # Raw driver SQL: sa.text() would read ":word" inside the password as a bind param.
    op.get_bind().exec_driver_sql(str(statement))


def upgrade() -> None:
    op.execute(_CREATE_ROLE)
    op.execute(_on_database("GRANT CONNECT ON DATABASE %I TO " + APP_ROLE))
    for schema in APP_SCHEMAS:
        op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {APP_ROLE}")
        op.execute(f"GRANT {_TABLE_PRIVILEGES} ON ALL TABLES IN SCHEMA {schema} TO {APP_ROLE}")
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {APP_ROLE}")
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
            f"GRANT {_TABLE_PRIVILEGES} ON TABLES TO {APP_ROLE}"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
            f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
        )
    password = os.environ.get(PASSWORD_ENV)
    if password:
        _enable_login(password)


def downgrade() -> None:
    # Revoke everything this migration granted; the role itself is cluster-wide
    # and may own grants in other databases, so it is dropped only if unused.
    for schema in APP_SCHEMAS:
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
            f"REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
            f"REVOKE {_TABLE_PRIVILEGES} ON TABLES FROM {APP_ROLE}"
        )
        op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {schema} FROM {APP_ROLE}")
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM {APP_ROLE}")
        op.execute(f"REVOKE USAGE ON SCHEMA {schema} FROM {APP_ROLE}")
    op.execute(_on_database("REVOKE CONNECT ON DATABASE %I FROM " + APP_ROLE))
    op.execute(
        f"""
        DO $$
        BEGIN
            DROP ROLE IF EXISTS {APP_ROLE};
        EXCEPTION WHEN dependent_objects_still_exist THEN
            RAISE NOTICE '{APP_ROLE} still has privileges elsewhere; not dropped';
        END
        $$
        """
    )
