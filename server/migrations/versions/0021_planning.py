"""Migration ``0021_planning``: plans, phases, tasks and task dependencies.

Tables in the ``planning`` schema (created by ``0001_initial``):

- ``plans``: one plan of an idea per spec version, ``draft`` until marked ``ready``.
- ``phases``: the ordered groups of a plan (``position`` from 0).
- ``tasks``: the work items, ordered inside their phase, with a Fibonacci ``estimate``
  (1, 2, 3, 5, 8) and an optional parent task.
- ``task_deps``: ``task_id`` cannot start before ``blocked_by_task_id`` is done.

Every table is a tenant table (RLS). Composite foreign keys keep a task's phase, parent and
dependencies inside the task's own plan, so a dangling or cross-plan link cannot be stored.
Positions are unique per parent but checked at commit (deferrable), so a reorder can move rows
in any order. ``metis_app`` gets the four DML grants; a ready plan is protected by the service.
The downgrade drops the tables and revokes the grants; the empty schema stays, as
``0001_initial`` owns it.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_planning"
down_revision = "0020_spec_versions"
branch_labels = None
depends_on = None

APP_ROLE = "metis_app"
SCHEMA = "planning"
STATUSES = ("draft", "ready")
ESTIMATES = (1, 2, 3, 5, 8)
TABLES = ("plans", "phases", "tasks", "task_deps")


def _in_list(column: str, values: tuple[object, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid(name: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def _fk(
    table: str,
    columns: list[str],
    target: str,
    target_columns: list[str],
    name: str,
    *,
    cascade: bool = True,
) -> sa.ForeignKeyConstraint:
    """A foreign key. Links between rows of one plan do not cascade, so removing a phase or a
    task can never silently remove what points at it (the plan's own delete still clears all)."""
    return sa.ForeignKeyConstraint(
        columns,
        [f"{target}.{c}" for c in target_columns],
        name=f"fk_{table}_{name}",
        ondelete="CASCADE" if cascade else None,
    )


def upgrade() -> None:
    op.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {APP_ROLE}")
    _create_plans()
    _create_phases()
    _create_tasks()
    _create_task_deps()
    for table in TABLES:
        op.execute(f"SELECT enable_tenant_rls('{SCHEMA}.{table}'::regclass)")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.{table} TO {APP_ROLE}")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table, schema=SCHEMA)
    op.execute(f"REVOKE USAGE ON SCHEMA {SCHEMA} FROM {APP_ROLE}")


def _create_plans() -> None:
    op.create_table(
        "plans",
        _uuid("id"),
        _uuid("workspace_id"),
        _uuid("idea_id"),
        _uuid("spec_version_id"),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_plans"),
        _fk("plans", ["workspace_id"], "identity.workspaces", ["id"], "workspace_id_workspaces"),
        _fk("plans", ["idea_id"], "ideas.ideas", ["id"], "idea_id_ideas"),
        sa.ForeignKeyConstraint(
            ["spec_version_id"],
            ["ideas.spec_versions.id"],
            name="fk_plans_spec_version_id_spec_versions",
        ),
        sa.CheckConstraint(_in_list("status", STATUSES), name="ck_plans_status"),
        sa.CheckConstraint("version >= 1", name="ck_plans_version"),
        sa.CheckConstraint("(status = 'ready') = (ready_at IS NOT NULL)", name="ck_plans_ready_at"),
        sa.UniqueConstraint("idea_id", "spec_version_id", name="uq_plans_idea_spec_version"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_plans_workspace_idea",
        "plans",
        ["workspace_id", "idea_id", sa.text("created_at DESC")],
        schema=SCHEMA,
    )


def _create_phases() -> None:
    op.create_table(
        "phases",
        _uuid("id"),
        _uuid("workspace_id"),
        _uuid("plan_id"),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("exit_criteria", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_phases"),
        _fk("phases", ["workspace_id"], "identity.workspaces", ["id"], "workspace_id_workspaces"),
        _fk("phases", ["plan_id"], f"{SCHEMA}.plans", ["id"], "plan_id_plans"),
        sa.CheckConstraint("position >= 0", name="ck_phases_position"),
        sa.UniqueConstraint("id", "plan_id", name="uq_phases_id_plan"),
        sa.UniqueConstraint(
            "plan_id",
            "position",
            name="uq_phases_plan_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        schema=SCHEMA,
    )


def _create_tasks() -> None:
    op.create_table(
        "tasks",
        _uuid("id"),
        _uuid("workspace_id"),
        _uuid("plan_id"),
        _uuid("phase_id"),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("estimate", sa.SmallInteger(), nullable=False),
        sa.Column(
            "labels", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")
        ),
        _uuid("parent_task_id", nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
        _fk("tasks", ["workspace_id"], "identity.workspaces", ["id"], "workspace_id_workspaces"),
        _fk("tasks", ["plan_id"], f"{SCHEMA}.plans", ["id"], "plan_id_plans"),
        _fk(
            "tasks",
            ["phase_id", "plan_id"],
            f"{SCHEMA}.phases",
            ["id", "plan_id"],
            "phase_id_phases",
            cascade=False,
        ),
        _fk(
            "tasks",
            ["parent_task_id", "plan_id"],
            f"{SCHEMA}.tasks",
            ["id", "plan_id"],
            "parent_task_id_tasks",
            cascade=False,
        ),
        sa.CheckConstraint("position >= 0", name="ck_tasks_position"),
        sa.CheckConstraint(_in_list("estimate", ESTIMATES), name="ck_tasks_estimate"),
        sa.CheckConstraint("parent_task_id IS DISTINCT FROM id", name="ck_tasks_parent"),
        sa.UniqueConstraint("id", "plan_id", name="uq_tasks_id_plan"),
        sa.UniqueConstraint(
            "phase_id",
            "position",
            name="uq_tasks_phase_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_tasks_plan", "tasks", ["plan_id"], schema=SCHEMA)


def _create_task_deps() -> None:
    op.create_table(
        "task_deps",
        _uuid("workspace_id"),
        _uuid("plan_id"),
        _uuid("task_id"),
        _uuid("blocked_by_task_id"),
        sa.PrimaryKeyConstraint("task_id", "blocked_by_task_id", name="pk_task_deps"),
        _fk(
            "task_deps",
            ["workspace_id"],
            "identity.workspaces",
            ["id"],
            "workspace_id_workspaces",
        ),
        _fk("task_deps", ["plan_id"], f"{SCHEMA}.plans", ["id"], "plan_id_plans"),
        _fk(
            "task_deps",
            ["task_id", "plan_id"],
            f"{SCHEMA}.tasks",
            ["id", "plan_id"],
            "task_id_tasks",
            cascade=False,
        ),
        _fk(
            "task_deps",
            ["blocked_by_task_id", "plan_id"],
            f"{SCHEMA}.tasks",
            ["id", "plan_id"],
            "blocked_by_task_id_tasks",
            cascade=False,
        ),
        sa.CheckConstraint("task_id <> blocked_by_task_id", name="ck_task_deps_self"),
        schema=SCHEMA,
    )
    op.create_index("ix_task_deps_blocked_by", "task_deps", ["blocked_by_task_id"], schema=SCHEMA)
    op.create_index("ix_task_deps_plan", "task_deps", ["plan_id"], schema=SCHEMA)
