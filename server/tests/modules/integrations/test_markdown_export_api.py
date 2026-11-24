"""Export Markdown route at the HTTP seam, on real Postgres as ``metis_app``.

What the file looks like is covered by the snapshot in
``tests/modules/integrations/snapshots``; these tests check what only the route knows:
who may read, which data it picks, the headers and the errors.
"""

from __future__ import annotations

from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.helpers.ids import uuid7
from metis.modules import ideas, scoring
from metis.modules.ideas import NewSpecVersion, SpecSource
from metis.modules.scoring import ScoreTrigger
from tests.helpers.auth import assert_problem
from tests.modules.ideas.idea_helpers import IDEAS_URL, Caller, create, member_of, owner
from tests.modules.ideas.spec_helpers import DRAFT, draft_idea, set_stage
from tests.modules.planning.planning_helpers import latest_spec_id, save
from tests.modules.scoring.scoring_helpers import Sessions, in_workspace, marks

TABLE_COUNT_SQL = """
    SELECT (SELECT count(*) FROM planning.plans) + (SELECT count(*) FROM scoring.score_runs)
    + (SELECT count(*) FROM ideas.spec_versions) + (SELECT count(*) FROM core.outbox)
"""


async def _get(client: httpx.AsyncClient, caller: Caller, idea_id: str) -> httpx.Response:
    return await client.get(f"{IDEAS_URL}/{idea_id}/export.md", headers=caller.headers)


async def _confirm(client: httpx.AsyncClient, caller: Caller, idea_id: str) -> None:
    response = await client.post(
        f"{IDEAS_URL}/{idea_id}/spec/confirm", json={"number": 1}, headers=caller.headers
    )
    assert response.status_code == 202, response.text


async def _score(engine: AsyncEngine, sessions: Sessions, caller: Caller, idea_id: str) -> None:
    """Record a score through a finished run (an idea has one active run)."""
    workspace_id, idea, run_id = UUID(caller.workspace_id), UUID(idea_id), uuid7()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ideas.workflow_runs (id, workspace_id, idea_id, status) "
                "VALUES (:id, :ws, :idea, 'succeeded')"
            ),
            {"id": run_id, "ws": workspace_id, "idea": idea},
        )
    async with in_workspace(sessions, workspace_id) as session:
        await scoring.record_score(
            session, workspace_id, idea, run_id, marks(7), ScoreTrigger.MANUAL
        )


async def _exportable(
    client: httpx.AsyncClient, engine: AsyncEngine, sessions: Sessions
) -> tuple[Caller, dict[str, str]]:
    """An owner and their idea: confirmed spec, a draft plan and a score."""
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, sessions, ada)
    await _confirm(client, ada, idea["id"])
    await save(sessions, ada, idea["id"], await latest_spec_id(client, ada, idea["id"]))
    await _score(engine, sessions, ada, idea["id"])
    return ada, idea


async def test_a_member_downloads_the_file_with_a_name_made_from_the_title(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, idea = await _exportable(client, engine, app_sessions)
    bob = await member_of(client, engine, ada)

    response = await _get(client, bob, idea["id"])

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="pocket-crm-plan.md"'
    body = response.text
    assert body.startswith("# Pocket CRM\n")
    assert "Plan: draft, version 1" in body
    assert "**Total: 70 / 100**" in body
    assert "### Phase 1 — Phase 0" in body
    assert "```mermaid" in body


async def test_a_title_with_quotes_and_markup_gives_an_ascii_only_file_name(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada, title='"; <script>')
    await _confirm_after_spec(client, engine, app_sessions, ada, idea)

    response = await _get(client, ada, idea["id"])

    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == 'attachment; filename="script-plan.md"'


async def _confirm_after_spec(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: Sessions,
    caller: Caller,
    idea: dict[str, str],
) -> None:
    """Give ``idea`` a confirmed spec and a plan (the idea comes from ``create``)."""
    await set_stage(engine, idea["id"], "spec_draft")
    workspace_id = UUID(caller.workspace_id)
    async with in_workspace(sessions, workspace_id) as session:
        await ideas.save_spec_version(
            session,
            workspace_id,
            UUID(idea["id"]),
            NewSpecVersion(content_md=DRAFT, source=SpecSource.AGENT),
        )
    await _confirm(client, caller, idea["id"])
    await save(sessions, caller, idea["id"], await latest_spec_id(client, caller, idea["id"]))


async def test_an_idea_that_was_never_scored_still_exports(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)
    await _confirm(client, ada, idea["id"])
    await save(app_sessions, ada, idea["id"], await latest_spec_id(client, ada, idea["id"]))

    response = await _get(client, ada, idea["id"])

    assert response.status_code == 200, response.text
    assert "Not scored." in response.text


async def test_an_idea_with_a_confirmed_spec_but_no_plan_is_a_conflict(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)
    await _confirm(client, ada, idea["id"])

    assert_problem(await _get(client, ada, idea["id"]), 409, "export.no_plan")


async def test_an_idea_without_a_confirmed_spec_is_a_conflict(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)

    assert_problem(await _get(client, ada, idea["id"]), 409, "export.no_plan")


async def test_an_unknown_idea_is_not_found(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ada = await owner(client, engine)

    assert_problem(await _get(client, ada, str(uuid7())), 404, "idea.not_found")


async def test_another_workspace_cannot_download_the_file(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    _, idea = await _exportable(client, engine, app_sessions)
    grace = await owner(client, engine, "grace")

    assert_problem(await _get(client, grace, idea["id"]), 404, "idea.not_found")


async def test_a_visitor_who_is_not_signed_in_is_refused(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    _, idea = await _exportable(client, engine, app_sessions)

    response = await client.get(f"{IDEAS_URL}/{idea['id']}/export.md")

    assert response.status_code == 401, response.text


async def test_downloading_writes_nothing(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, idea = await _exportable(client, engine, app_sessions)
    async with engine.connect() as conn:
        before = (await conn.execute(text(TABLE_COUNT_SQL))).scalar_one()

    assert (await _get(client, ada, idea["id"])).status_code == 200
    assert (await _get(client, ada, idea["id"])).status_code == 200

    async with engine.connect() as conn:
        after = (await conn.execute(text(TABLE_COUNT_SQL))).scalar_one()
    assert after == before
