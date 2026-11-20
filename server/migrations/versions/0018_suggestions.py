"""Migration ``0018_suggestions``: the Advisor's suggestions, and the merge of two heads.

``0017_scoring`` and ``0017_run_user_prompt`` both follow ``0016_research``; this revision
joins them.

Table ``scoring.suggestions`` (the schema comes from ``0001_initial``): one improvement the
Advisor made from a score run, with its kind, reason, the parameters it targets, the expected
impact and at least one source. Tenant table with RLS. ``metis_app`` gets ``SELECT`` and
``INSERT``, and ``UPDATE`` on ``status`` only, so a suggestion's text cannot be changed or
deleted through the app role. The downgrade drops the table.
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_suggestions"
down_revision = ("0017_scoring", "0017_run_user_prompt")
branch_labels = None
depends_on = None

APP_ROLE = "metis_app"
SCHEMA = "scoring"
TABLE = "suggestions"
KINDS = ("feature", "niche", "pricing", "pivot")
STATUSES = ("open", "accepted", "dismissed")
PARAMS = (
    "problem_severity",
    "uniqueness",
    "market_demand",
    "value",
    "feasibility",
    "timing",
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid(name: str) -> sa.Column[object]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=False)


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def _fk(column: str, target: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [target], name=f"fk_{TABLE}_{column}_{name}", ondelete="CASCADE"
    )


def upgrade() -> None:
    op.create_table(
        TABLE,
        _uuid("id"),
        _uuid("workspace_id"),
        _uuid("idea_id"),
        _uuid("score_run_id"),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("target_params", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("expected_impact", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name=f"pk_{TABLE}"),
        _fk("workspace_id", "identity.workspaces.id", "workspaces"),
        _fk("idea_id", "ideas.ideas.id", "ideas"),
        _fk("score_run_id", f"{SCHEMA}.score_runs.id", "score_runs"),
        sa.CheckConstraint(_in_list("kind", KINDS), name=f"ck_{TABLE}_kind"),
        sa.CheckConstraint(_in_list("status", STATUSES), name=f"ck_{TABLE}_status"),
        sa.CheckConstraint(
            "cardinality(target_params) BETWEEN 1 AND 3 "
            f"AND target_params <@ ARRAY[{', '.join(repr(p) for p in PARAMS)}]::text[]",
            name=f"ck_{TABLE}_target_params",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence) = 'array' AND jsonb_array_length(evidence) >= 1",
            name=f"ck_{TABLE}_evidence",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        f"ix_{TABLE}_workspace_idea",
        TABLE,
        ["workspace_id", "idea_id", sa.text("score_run_id DESC")],
        schema=SCHEMA,
    )
    op.create_index(f"ix_{TABLE}_score_run", TABLE, ["score_run_id"], schema=SCHEMA)
    op.execute(f"SELECT enable_tenant_rls('{SCHEMA}.{TABLE}'::regclass)")
    op.execute(f"GRANT SELECT, INSERT ON {SCHEMA}.{TABLE} TO {APP_ROLE}")
    op.execute(f"GRANT UPDATE (status) ON {SCHEMA}.{TABLE} TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
