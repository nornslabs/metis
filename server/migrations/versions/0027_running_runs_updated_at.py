"""``ideas.list_running_runs()`` also returns ``updated_at``.

Run recovery skips a run that moved a moment ago (a worker may be about to take its lock)
and fails a run that made no progress for too long, so it needs the last update time.
The function is dropped and created again because its return type changes; it keeps its
``SECURITY DEFINER`` rule, its ``search_path`` and its grants (``metis_app`` alone).

The downgrade restores the two-column version.
"""

from alembic import op

revision = "0027_running_runs_updated_at"
down_revision = "0026_export_partial"
branch_labels = None
depends_on = None

APP_ROLE = "metis_app"
FUNCTION = "ideas.list_running_runs()"


def _create(columns: str, select: str) -> tuple[str, ...]:
    return (
        f"DROP FUNCTION IF EXISTS {FUNCTION}",
        f"""
        CREATE FUNCTION {FUNCTION}
        RETURNS TABLE ({columns})
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = ideas, pg_catalog
        AS $$ SELECT {select} FROM ideas.workflow_runs WHERE status = 'running' $$
        """,
        f"REVOKE ALL ON FUNCTION {FUNCTION} FROM PUBLIC",
        f"GRANT EXECUTE ON FUNCTION {FUNCTION} TO {APP_ROLE}",
    )


def upgrade() -> None:
    for statement in _create(
        "run_id uuid, workspace_id uuid, updated_at timestamptz", "id, workspace_id, updated_at"
    ):
        op.execute(statement)


def downgrade() -> None:
    for statement in _create("run_id uuid, workspace_id uuid", "id, workspace_id"):
        op.execute(statement)
