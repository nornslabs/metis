"""Seeds one eval case into a throwaway workspace, and removes it again.

Written as the database owner and as a superuser (like the migrations and the test fixtures), so
row-level security does not get in the way; a non-superuser owner fails with an RLS error. The
run itself goes through ``run_graph`` as ``metis_app``. Evals are a developer tool outside the
``metis`` import contracts: seeding uses raw SQL and ``identity``'s ``set_key`` directly.
Everything a case makes lives in one workspace owned by one throwaway user, and
``remove_case`` deletes both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from evals.cases import Case, CaseSnapshot
from evals.report import Usage
from metis.helpers.ids import uuid7
from metis.modules import auth, identity
from metis.modules.ideas import InterviewBrief, InterviewEnd, InterviewTopic
from metis.modules.identity import MemberRole, Membership, ProviderKind
from metis.modules.identity.service.provider_keys import set_key

if TYPE_CHECKING:
    from uuid import UUID

SCORING_STAGE = "scoring"
CHECKLIST = (
    InterviewTopic.PROBLEM,
    InterviewTopic.SOLUTION,
    InterviewTopic.CUSTOMER,
    InterviewTopic.PAYMENT,
    InterviewTopic.FEASIBILITY,
)
CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


@dataclass(frozen=True)
class LlmConfig:
    """The model the eval workspace scores with."""

    base_url: str
    api_key: str
    model: str


@dataclass(frozen=True)
class Seeded:
    user_id: UUID
    workspace_id: UUID
    idea_id: UUID
    run_id: UUID


async def seed_case(engine: AsyncEngine, case: Case, llm: LlmConfig) -> Seeded:
    """A workspace with the case's idea at ``scoring``, its interview, research and a queued run."""
    user_id = await _create_user(engine, case)
    workspace_id = await _create_workspace(engine, user_id, llm)
    idea_id, run_id = uuid7(), uuid7()
    async with engine.begin() as conn:
        await _insert_idea(conn, case, workspace_id, user_id, idea_id)
        await conn.execute(
            text(
                "INSERT INTO ideas.workflow_runs (id, workspace_id, idea_id) "
                "VALUES (:id, :ws, :idea)"
            ),
            {"id": run_id, "ws": workspace_id, "idea": idea_id},
        )
        await _insert_turns(conn, case, workspace_id, idea_id, run_id)
        if case.snapshot is not None:
            await _insert_snapshot(conn, case.snapshot, workspace_id, idea_id, run_id)
    return Seeded(user_id, workspace_id, idea_id, run_id)


async def usage_of(engine: AsyncEngine, seeded: Seeded) -> Usage:
    """Tokens and cost the run's model calls recorded."""
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT coalesce(sum(input_tokens), 0), coalesce(sum(output_tokens), 0), "
                    "sum(cost_usd) FROM ideas.llm_usage WHERE workspace_id = :ws"
                ),
                {"ws": seeded.workspace_id},
            )
        ).one()
    return Usage(int(row[0]), int(row[1]), row[2])


async def remove_case(engine: AsyncEngine, seeded: Seeded) -> None:
    """Delete the case's workspace (rows cascade), its checkpoints and its user."""
    async with engine.begin() as conn:
        for table in CHECKPOINT_TABLES:
            await conn.execute(
                text(f"DELETE FROM agent.{table} WHERE thread_id = :thread"),
                {"thread": str(seeded.run_id)},
            )
        # The outbox has no foreign key to the workspace, so its rows are not cascaded.
        await conn.execute(
            text("DELETE FROM core.outbox WHERE workspace_id = :ws"), {"ws": seeded.workspace_id}
        )
        await conn.execute(
            text("DELETE FROM identity.workspaces WHERE id = :ws"), {"ws": seeded.workspace_id}
        )
        await conn.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": seeded.user_id})


async def _create_user(engine: AsyncEngine, case: Case) -> UUID:
    user_id = uuid7()
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO auth.users (id, email, name) VALUES (:id, :email, :name)"),
            {"id": user_id, "email": f"eval-{case.id}-{user_id}@eval.invalid", "name": "Eval"},
        )
    return user_id


async def _create_workspace(engine: AsyncEngine, user_id: UUID, llm: LlmConfig) -> UUID:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = await auth.get_user(session, user_id)
        if user is None:
            raise RuntimeError(f"eval user {user_id} vanished after it was created")
        workspace = await identity.ensure_personal_workspace(session, user)
        owner = Membership(workspace=workspace, role=MemberRole.OWNER)
        await set_key(session, owner, ProviderKind.LLM, llm.api_key, llm.base_url, llm.model)
        await session.commit()
    return workspace.id


async def _insert_idea(
    conn: AsyncConnection, case: Case, workspace_id: UUID, user_id: UUID, idea_id: UUID
) -> None:
    answered = {InterviewTopic(a.topic) for a in case.answers}
    brief = InterviewBrief(
        **case.brief.model_dump(),
        covered=tuple(t for t in CHECKLIST if t in answered),
        missing=tuple(t for t in CHECKLIST if t not in answered),
        ended_by=InterviewEnd.COVERAGE,
        question_count=len(case.answers),
    )
    await conn.execute(
        text(
            "INSERT INTO ideas.ideas (id, workspace_id, created_by, title, raw_text, stage, "
            "interview_brief) VALUES (:id, :ws, :by, :title, :raw, :stage, "
            "CAST(:brief AS jsonb))"
        ),
        {
            "id": idea_id,
            "ws": workspace_id,
            "by": user_id,
            "title": case.title,
            "raw": case.idea_text,
            "stage": SCORING_STAGE,
            "brief": brief.model_dump_json(),
        },
    )


async def _insert_turns(
    conn: AsyncConnection, case: Case, workspace_id: UUID, idea_id: UUID, run_id: UUID
) -> None:
    for answer in case.answers:
        await conn.execute(
            text(
                "INSERT INTO ideas.interview_turns (id, workspace_id, idea_id, run_id, topic, "
                "source, question, answer) VALUES (:id, :ws, :idea, :run, :topic, 'asked', "
                ":question, :answer)"
            ),
            {
                "id": uuid7(),
                "ws": workspace_id,
                "idea": idea_id,
                "run": run_id,
                "topic": answer.topic,
                "question": answer.question,
                "answer": answer.answer,
            },
        )


async def _insert_snapshot(
    conn: AsyncConnection, snapshot: CaseSnapshot, workspace_id: UUID, idea_id: UUID, run_id: UUID
) -> None:
    snapshot_id = uuid7()
    await conn.execute(
        text(
            "INSERT INTO research.snapshots (id, workspace_id, idea_id, run_id, summary, "
            "closed_at) VALUES (:id, :ws, :idea, :run, :summary, now())"
        ),
        {
            "id": snapshot_id,
            "ws": workspace_id,
            "idea": idea_id,
            "run": run_id,
            "summary": snapshot.summary,
        },
    )
    for item in snapshot.items:
        await conn.execute(
            text(
                "INSERT INTO research.items (id, workspace_id, snapshot_id, kind, title, url, "
                "quote, claim, confidence) VALUES (:id, :ws, :snap, :kind, :title, :url, "
                ":quote, :claim, :confidence)"
            ),
            {
                "id": uuid7(),
                "ws": workspace_id,
                "snap": snapshot_id,
                **item.model_dump(),
            },
        )
    for rival in snapshot.competitors:
        competitor_id = uuid7()
        await conn.execute(
            text(
                "INSERT INTO research.competitors (id, workspace_id, name, url, domain, "
                "description, pricing) VALUES (:id, :ws, :name, :url, :domain, :description, "
                ":pricing)"
            ),
            {
                "id": competitor_id,
                "ws": workspace_id,
                "name": rival.name,
                "url": rival.url,
                "domain": urlparse(rival.url).netloc,
                "description": rival.description,
                "pricing": rival.pricing,
            },
        )
        await conn.execute(
            text(
                "INSERT INTO research.idea_competitors (snapshot_id, competitor_id, "
                "workspace_id, idea_id, overlap) VALUES (:snap, :comp, :ws, :idea, :overlap)"
            ),
            {
                "snap": snapshot_id,
                "comp": competitor_id,
                "ws": workspace_id,
                "idea": idea_id,
                "overlap": rival.overlap,
            },
        )
