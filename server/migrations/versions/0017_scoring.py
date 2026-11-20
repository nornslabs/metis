"""Migration ``0017_scoring``: the fixed rubric and immutable score runs.

Tables in the ``scoring`` schema (created by ``0001_initial``):

- ``rubric_versions``: the weights a score was computed with, one row per version. Global
  (no ``workspace_id``, no RLS); version 1 is seeded here. ``metis_app`` can only read it.
- ``score_runs``: one score of an idea, written by one workflow run, with its ``total``
  (0–100) and ``band``.
- ``score_params``: the six per-parameter results of a score run (raw mark, weighted
  points, reason, confidence, evidence). ``no_evidence`` is true exactly when ``evidence``
  is empty.

The two tenant tables get RLS through ``enable_tenant_rls``. ``metis_app`` gets ``SELECT``
and ``INSERT`` only on them, so a score run cannot be changed or deleted through the app
role. The downgrade drops the tables and revokes the grants; the empty schema stays, as
``0001_initial`` owns it.
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017_scoring"
down_revision = "0016_research"
branch_labels = None
depends_on = None

APP_ROLE = "metis_app"
SCHEMA = "scoring"
WORKSPACES = "identity.workspaces.id"
RUBRIC_V1: dict[str, int] = {
    "problem_severity": 25,
    "uniqueness": 25,
    "market_demand": 15,
    "value": 15,
    "feasibility": 10,
    "timing": 10,
}
TRIGGERS = ("manual", "scheduled", "signal")
BANDS = ("build", "promising", "advise")
TENANT_TABLES = ("score_runs", "score_params")

SCHEMA_UP_SQL: tuple[str, ...] = (f"GRANT USAGE ON SCHEMA {SCHEMA} TO {APP_ROLE}",)
SCHEMA_DOWN_SQL: tuple[str, ...] = (f"REVOKE USAGE ON SCHEMA {SCHEMA} FROM {APP_ROLE}",)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid(name: str) -> sa.Column[object]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=False)


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def _fk(column: str, target: str, table: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [target], name=f"fk_{table}_{column}_{name}", ondelete="CASCADE"
    )


def upgrade() -> None:
    for statement in SCHEMA_UP_SQL:
        op.execute(statement)
    _create_rubric_versions()
    _create_score_runs()
    _create_score_params()
    for table in TENANT_TABLES:
        op.execute(f"SELECT enable_tenant_rls('{SCHEMA}.{table}'::regclass)")
        op.execute(f"GRANT SELECT, INSERT ON {SCHEMA}.{table} TO {APP_ROLE}")
    op.execute(f"GRANT SELECT ON {SCHEMA}.rubric_versions TO {APP_ROLE}")


def downgrade() -> None:
    for table in ("score_params", "score_runs", "rubric_versions"):
        op.drop_table(table, schema=SCHEMA)
    for statement in SCHEMA_DOWN_SQL:
        op.execute(statement)


def _create_rubric_versions() -> None:
    table = op.create_table(
        "rubric_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("weights", postgresql.JSONB(), nullable=False),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_rubric_versions"),
        schema=SCHEMA,
    )
    op.bulk_insert(table, [{"id": 1, "weights": RUBRIC_V1}])


def _create_score_runs() -> None:
    op.create_table(
        "score_runs",
        _uuid("id"),
        _uuid("workspace_id"),
        _uuid("idea_id"),
        _uuid("run_id"),
        sa.Column("rubric_version_id", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("band", sa.Text(), nullable=False),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_score_runs"),
        _fk("workspace_id", WORKSPACES, "score_runs", "workspaces"),
        _fk("idea_id", "ideas.ideas.id", "score_runs", "ideas"),
        _fk("run_id", "ideas.workflow_runs.id", "score_runs", "workflow_runs"),
        sa.ForeignKeyConstraint(
            ["rubric_version_id"],
            [f"{SCHEMA}.rubric_versions.id"],
            name="fk_score_runs_rubric_version_id_rubric_versions",
        ),
        sa.CheckConstraint(_in_list("trigger", TRIGGERS), name="ck_score_runs_trigger"),
        sa.CheckConstraint("total BETWEEN 0 AND 100", name="ck_score_runs_total"),
        sa.CheckConstraint(_in_list("band", BANDS), name="ck_score_runs_band"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_score_runs_workspace_idea",
        "score_runs",
        ["workspace_id", "idea_id", sa.text("id DESC")],
        schema=SCHEMA,
    )


def _create_score_params() -> None:
    op.create_table(
        "score_params",
        _uuid("score_run_id"),
        _uuid("workspace_id"),
        sa.Column("param", sa.Text(), nullable=False),
        sa.Column("raw", sa.Integer(), nullable=False),
        sa.Column("weighted", sa.Numeric(5, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column("no_evidence", sa.Boolean(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("score_run_id", "param", name="pk_score_params"),
        _fk("score_run_id", f"{SCHEMA}.score_runs.id", "score_params", "score_runs"),
        _fk("workspace_id", WORKSPACES, "score_params", "workspaces"),
        sa.CheckConstraint(_in_list("param", tuple(RUBRIC_V1)), name="ck_score_params_param"),
        sa.CheckConstraint("raw BETWEEN 0 AND 10", name="ck_score_params_raw"),
        sa.CheckConstraint("weighted BETWEEN 0 AND 100", name="ck_score_params_weighted"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_score_params_confidence"),
        sa.CheckConstraint(
            "jsonb_typeof(evidence) = 'array' AND no_evidence = (jsonb_array_length(evidence) = 0)",
            name="ck_score_params_evidence_flag",
        ),
        schema=SCHEMA,
    )
