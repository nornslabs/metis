"""Migration ``0015_interview_turns``: the Interviewer's turns and the idea's interview brief.

``ideas.interview_turns`` is a tenant table (RLS through ``enable_tenant_rls``); ``metis_app``
gets DML through the default privileges ``0010_ideas`` set on the ``ideas`` schema. A turn
is ``asked`` (a question the user saw) or ``noted`` (a topic the Interviewer took from the
idea text or an earlier answer). A partial unique index allows one unanswered ``asked``
turn per run, so a node that re-runs on resume cannot open a second copy of its question.
Turns are ordered by their uuid7 ``id``.

``ideas.ideas.interview_brief`` holds the latest ``InterviewBrief`` (jsonb, null until an
interview finishes; a later interview overwrites it, the turns keep the history).

The downgrade drops the column and the table.
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_interview_turns"
down_revision = "0014_run_active_index"
branch_labels = None
depends_on = None

SCHEMA = "ideas"
TABLE = "interview_turns"
IDEAS_TABLE = "ideas"
BRIEF_COLUMN = "interview_brief"
OPEN_QUESTION_INDEX = "uq_interview_turns_open_question"
TOPICS = ("problem", "solution", "customer", "payment", "feasibility", "other")
SOURCES = ("asked", "noted")
RLS_SQL = f"SELECT enable_tenant_rls('{SCHEMA}.{TABLE}'::regclass)"


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idea_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_interview_turns"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["identity.workspaces.id"],
            name="fk_interview_turns_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["idea_id"],
            [f"{SCHEMA}.ideas.id"],
            name="fk_interview_turns_idea_id_ideas",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{SCHEMA}.workflow_runs.id"],
            name="fk_interview_turns_run_id_workflow_runs",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(_in_list("topic", TOPICS), name="ck_interview_turns_topic"),
        sa.CheckConstraint(_in_list("source", SOURCES), name="ck_interview_turns_source"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_interview_turns_workspace_idea", TABLE, ["workspace_id", "idea_id", "id"], schema=SCHEMA
    )
    op.create_index("ix_interview_turns_run_id", TABLE, ["run_id"], schema=SCHEMA)
    op.create_index(
        OPEN_QUESTION_INDEX,
        TABLE,
        ["run_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where="source = 'asked' AND answer IS NULL",
    )
    op.execute(RLS_SQL)
    op.add_column(
        IDEAS_TABLE, sa.Column(BRIEF_COLUMN, postgresql.JSONB(), nullable=True), schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_column(IDEAS_TABLE, BRIEF_COLUMN, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
