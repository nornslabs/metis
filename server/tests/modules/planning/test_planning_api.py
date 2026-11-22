"""Plan routes at the HTTP seam, on real Postgres as ``metis_app``.

The Planner saves plans through the module's service (its path); everything a member does goes
over HTTP. Plans hang on an idea at ``spec_draft`` with the Architect's version 1.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.core.errors import (
    IdeaNotFoundError,
    InvalidPlanError,
    PlanNotEditableError,
    SpecNotFoundError,
)
from metis.modules.planning import Plan
from tests.helpers.auth import assert_problem
from tests.modules.ideas.idea_helpers import IDEAS_URL, Caller, create, member_of, owner
from tests.modules.ideas.spec_helpers import DRAFT, draft_idea
from tests.modules.planning.planning_helpers import (
    dep,
    latest_spec_id,
    plan_input,
    plan_ready_events,
    plan_url,
    planned,
    save,
    task,
    task_id,
    titles,
)
from tests.modules.scoring.scoring_helpers import Sessions


async def _get(
    client: httpx.AsyncClient, caller: Caller, idea_id: str, query: str = ""
) -> httpx.Response:
    return await client.get(f"{IDEAS_URL}/{idea_id}/plan{query}", headers=caller.headers)


# ------------------------------------------------------------------------------ read


async def test_a_plan_is_read_with_phases_tasks_dependencies_and_critical_path(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, idea, spec_id, _ = await planned(client, engine, app_sessions)
    # The default plan ties: a then c is 3 + 2 = 5 points, the same as the lone b, and a tie
    # goes to the earlier task. A bigger c makes the chain the critical path.
    plan = await save(
        app_sessions,
        ada,
        idea["id"],
        spec_id,
        plan_input([task("a"), task("b", estimate=5), task("c", phase=1, estimate=3)]),
    )

    response = await _get(client, ada, idea["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["id"], body["status"], body["version"]) == (str(plan.id), "draft", 2)
    assert body["spec_version_id"] == str(spec_id)
    assert titles(body) == [["Task a", "Task b"], ["Task c"]]
    assert [p["name"] for p in body["phases"]] == ["Phase 0", "Phase 1"]
    c = body["phases"][1]["tasks"][0]
    assert c["blocked_by"] == [str(task_id(plan, "a"))]
    assert body["critical_path"] == {
        "task_ids": [str(task_id(plan, "a")), str(task_id(plan, "c"))],
        "points": 6,
    }


async def test_a_plan_without_dependencies_has_the_largest_task_as_its_path(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)
    spec_id = await latest_spec_id(client, ada, idea["id"])
    plan = await save(
        app_sessions, ada, idea["id"], spec_id, plan_input([task("a"), task("b", estimate=8)])
    )

    body = (await _get(client, ada, idea["id"])).json()

    assert body["critical_path"] == {"task_ids": [str(task_id(plan, "b"))], "points": 8}


async def test_an_idea_without_a_plan_has_none(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)

    assert_problem(await _get(client, ada, idea["id"]), 404, "plan.not_found")


async def test_an_unknown_idea_is_not_found(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ada = await owner(client, engine)

    assert_problem(await _get(client, ada, str(uuid4())), 404, "idea.not_found")


async def test_a_new_spec_version_gets_its_own_plan_and_the_newest_is_the_default(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, idea, first_spec, first = await planned(client, engine, app_sessions)
    edit = await client.post(
        f"{IDEAS_URL}/{idea['id']}/spec/versions",
        json={"base_number": 1, "content_md": DRAFT + "\n"},
        headers=ada.headers,
    )
    assert edit.status_code == 201, edit.text
    second_spec = UUID(edit.json()["id"])
    second = await save(app_sessions, ada, idea["id"], second_spec, plan_input([task("z")]))

    newest = (await _get(client, ada, idea["id"])).json()
    older = (await _get(client, ada, idea["id"], f"?spec_version_id={first_spec}")).json()

    assert second.id != first.id
    assert newest["id"] == str(second.id)
    assert older["id"] == str(first.id)


async def test_another_workspace_cannot_see_or_change_the_plan(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    _, idea, _, plan = await planned(client, engine, app_sessions)
    grace = await owner(client, engine, "grace")

    assert_problem(await _get(client, grace, idea["id"]), 404, "idea.not_found")
    edit = await client.post(plan_url(plan.id, "/ready"), headers=grace.headers)
    assert_problem(edit, 404, "plan.not_found")


async def test_any_member_reads_edits_and_marks_ready(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, idea, _, plan = await planned(client, engine, app_sessions)
    bob = await member_of(client, engine, ada)

    assert (await _get(client, bob, idea["id"])).status_code == 200
    renamed = await client.patch(
        plan_url(plan.id, "/phases"),
        json={
            "version": 1,
            "ops": [{"op": "rename", "phase_id": str(plan.phases[0].id), "name": "Build"}],
        },
        headers=bob.headers,
    )
    assert renamed.status_code == 200, renamed.text
    ready = await client.post(plan_url(plan.id, "/ready"), headers=bob.headers)
    assert ready.status_code == 200, ready.text


# -------------------------------------------------------------------------- save_plan


async def test_saving_again_replaces_the_draft_in_place(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, idea, spec_id, first = await planned(client, engine, app_sessions)

    second = await save(
        app_sessions, ada, idea["id"], spec_id, plan_input([task("only")], phases=1)
    )

    assert (second.id, second.version) == (first.id, 2)
    body = (await _get(client, ada, idea["id"])).json()
    assert titles(body) == [["Task only"]]
    async with engine.connect() as conn:
        counts = (
            await conn.execute(
                text(
                    "SELECT (SELECT count(*) FROM planning.tasks), "
                    "(SELECT count(*) FROM planning.phases), "
                    "(SELECT count(*) FROM planning.task_deps)"
                )
            )
        ).one()
    assert tuple(counts) == (1, 1, 0)


@pytest.mark.parametrize(
    ("tasks", "deps", "reason"),
    [
        ([task("a", estimate=13)], [], "bad_estimate"),
        ([task("a"), task("b")], [dep("a", "b"), dep("b", "a")], "dependency_cycle"),
        ([task("a")], [dep("a", "ghost")], "unknown_task"),
    ],
)
async def test_an_invalid_plan_is_refused_and_nothing_is_stored(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    app_sessions: Sessions,
    tasks,
    deps,
    reason: str,  # type: ignore[no-untyped-def]
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)
    spec_id = await latest_spec_id(client, ada, idea["id"])

    with pytest.raises(InvalidPlanError) as error:
        await save(app_sessions, ada, idea["id"], spec_id, plan_input(tasks, deps))

    assert (error.value.meta or {})["reason"] == reason
    assert_problem(await _get(client, ada, idea["id"]), 404, "plan.not_found")


async def test_a_spec_version_of_another_idea_is_refused(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, idea, _, _ = await planned(client, engine, app_sessions)
    other = await draft_idea(client, engine, app_sessions, ada)
    other_spec = await latest_spec_id(client, ada, other["id"])

    with pytest.raises(SpecNotFoundError):
        await save(app_sessions, ada, idea["id"], other_spec)


async def test_an_unknown_idea_cannot_beplanned(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, spec_id, _ = await planned(client, engine, app_sessions)

    with pytest.raises(IdeaNotFoundError):
        await save(app_sessions, ada, str(uuid4()), spec_id)


# ------------------------------------------------------------------------ phase edits


async def _edit_phases(
    client: httpx.AsyncClient, caller: Caller, plan_id: UUID, version: int, *ops: dict[str, object]
) -> httpx.Response:
    return await client.patch(
        plan_url(plan_id, "/phases"),
        json={"version": version, "ops": list(ops)},
        headers=caller.headers,
    )


async def test_phases_are_renamed_and_added_at_a_position(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    response = await _edit_phases(
        client,
        ada,
        plan.id,
        1,
        {"op": "rename", "phase_id": str(plan.phases[0].id), "name": "Build", "goal": "Ship it"},
        {"op": "add", "name": "Launch", "goal": "Go live", "exit_criteria": "Users", "position": 1},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == 2
    assert [p["name"] for p in body["phases"]] == ["Build", "Launch", "Phase 1"]
    assert [p["position"] for p in body["phases"]] == [0, 1, 2]
    assert body["phases"][0]["goal"] == "Ship it"
    assert titles(body) == [["Task a", "Task b"], [], ["Task c"]]


async def test_phases_are_reordered_and_their_tasks_follow(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)
    first, second = plan.phases[0].id, plan.phases[1].id

    response = await _edit_phases(
        client, ada, plan.id, 1, {"op": "reorder", "phase_ids": [str(second), str(first)]}
    )

    assert response.status_code == 200, response.text
    assert titles(response.json()) == [["Task c"], ["Task a", "Task b"]]


async def test_removing_a_phase_moves_its_tasks_and_keeps_the_dependencies(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, idea, _, plan = await planned(client, engine, app_sessions)

    response = await _edit_phases(
        client,
        ada,
        plan.id,
        1,
        {
            "op": "remove",
            "phase_id": str(plan.phases[0].id),
            "move_tasks_to": str(plan.phases[1].id),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert titles(body) == [["Task c", "Task a", "Task b"]]
    c = body["phases"][0]["tasks"][0]
    assert c["blocked_by"] == [str(task_id(plan, "a"))]
    assert (await _get(client, ada, idea["id"])).json()["version"] == 2


async def test_removing_a_phase_with_tasks_needs_somewhere_to_move_them(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    response = await _edit_phases(
        client, ada, plan.id, 1, {"op": "remove", "phase_id": str(plan.phases[0].id)}
    )

    assert_problem(response, 422, "plan.invalid_plan")
    assert response.json()["meta"]["reason"] == "bad_operation"


async def test_a_failing_op_changes_nothing_of_the_earlier_ones(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, idea, _, plan = await planned(client, engine, app_sessions)

    response = await _edit_phases(
        client,
        ada,
        plan.id,
        1,
        {"op": "rename", "phase_id": str(plan.phases[0].id), "name": "Renamed"},
        {"op": "remove", "phase_id": str(plan.phases[0].id)},
    )

    assert response.status_code == 422, response.text
    body = (await _get(client, ada, idea["id"])).json()
    assert (body["version"], body["phases"][0]["name"]) == (1, "Phase 0")


async def test_a_reorder_must_list_every_phase(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    response = await _edit_phases(
        client, ada, plan.id, 1, {"op": "reorder", "phase_ids": [str(plan.phases[0].id)]}
    )

    assert_problem(response, 422, "plan.invalid_plan")


async def test_an_unknown_phase_is_not_found(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    response = await _edit_phases(
        client, ada, plan.id, 1, {"op": "rename", "phase_id": str(uuid4()), "name": "X"}
    )

    assert_problem(response, 404, "plan.not_found")


# -------------------------------------------------------------------------- task edits


async def _edit_task(
    client: httpx.AsyncClient,
    caller: Caller,
    plan: Plan,
    title: str,
    version: int,
    **fields: object,
) -> httpx.Response:
    return await client.patch(
        plan_url(plan.id, f"/tasks/{task_id(plan, title)}"),
        json={"version": version, **fields},
        headers=caller.headers,
    )


async def test_a_task_is_edited(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    response = await _edit_task(
        client,
        ada,
        plan,
        "a",
        1,
        title="Renamed",
        estimate=8,
        labels=["backend"],
        description="More",
    )

    assert response.status_code == 200, response.text
    edited = response.json()["phases"][0]["tasks"][0]
    assert (edited["title"], edited["estimate"], edited["labels"], edited["description"]) == (
        "Renamed",
        8,
        ["backend"],
        "More",
    )
    assert response.json()["version"] == 2


async def test_a_task_moves_to_another_phase_and_keeps_its_dependencies(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    response = await _edit_task(
        client, ada, plan, "a", 1, phase_id=str(plan.phases[1].id), position=0
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert titles(body) == [["Task b"], ["Task a", "Task c"]]
    assert [t["position"] for t in body["phases"][0]["tasks"]] == [0]
    c = body["phases"][1]["tasks"][1]
    assert c["blocked_by"] == [str(task_id(plan, "a"))]


async def test_a_task_is_reordered_inside_its_phase(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    response = await _edit_task(client, ada, plan, "a", 1, position=1)

    assert titles(response.json())[0] == ["Task b", "Task a"]


@pytest.mark.parametrize("estimate", [0, 4, 13])
async def test_a_bad_estimate_on_a_task_is_refused(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions, estimate: int
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    response = await _edit_task(client, ada, plan, "a", 1, estimate=estimate)

    assert_problem(response, 422, "plan.invalid_plan")
    assert response.json()["meta"]["reason"] == "bad_estimate"


async def test_an_unknown_task_or_target_phase_is_not_found(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    ghost_task = await client.patch(
        plan_url(plan.id, f"/tasks/{uuid4()}"),
        json={"version": 1, "title": "X"},
        headers=ada.headers,
    )
    ghost_phase = await _edit_task(client, ada, plan, "a", 1, phase_id=str(uuid4()))

    assert_problem(ghost_task, 404, "plan.not_found")
    assert_problem(ghost_phase, 404, "plan.not_found")


async def test_an_empty_task_patch_is_refused(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    assert_problem(await _edit_task(client, ada, plan, "a", 1), 422, "validation_failed")


# ----------------------------------------------------------------------------- versions


async def test_an_edit_on_a_stale_version_is_a_conflict(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)
    assert (await _edit_task(client, ada, plan, "a", 1, title="One")).status_code == 200

    stale_task = await _edit_task(client, ada, plan, "b", 1, title="Two")
    stale_phases = await _edit_phases(
        client, ada, plan.id, 1, {"op": "rename", "phase_id": str(plan.phases[0].id), "name": "X"}
    )

    assert_problem(stale_task, 409, "plan.conflict")
    assert_problem(stale_phases, 409, "plan.conflict")


async def test_two_edits_on_one_version_one_wins_and_one_conflicts(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    first, second = await asyncio.gather(
        _edit_task(client, ada, plan, "a", 1, title="First"),
        _edit_task(client, ada, plan, "b", 1, title="Second"),
    )

    assert sorted([first.status_code, second.status_code]) == [200, 409]


# ----------------------------------------------------------------------------- ready


async def test_marking_ready_fixes_the_plan_and_emits_one_event(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, spec_id, plan = await planned(client, engine, app_sessions)

    first = await client.post(plan_url(plan.id, "/ready"), headers=ada.headers)
    again = await client.post(plan_url(plan.id, "/ready"), headers=ada.headers)

    assert first.status_code == again.status_code == 200
    body = first.json()
    assert (body["status"], body["version"]) == ("ready", 2)
    assert body["ready_at"] is not None
    assert again.json() == body
    assert await plan_ready_events(engine, ada) == [
        {
            "idea_id": str(plan.idea_id),
            "plan_id": str(plan.id),
            "spec_version_id": str(spec_id),
            "version": 2,
        }
    ]


async def test_a_ready_plan_cannot_be_edited_or_replaced(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, idea, spec_id, plan = await planned(client, engine, app_sessions)
    await client.post(plan_url(plan.id, "/ready"), headers=ada.headers)

    phases = await _edit_phases(
        client, ada, plan.id, 2, {"op": "rename", "phase_id": str(plan.phases[0].id), "name": "X"}
    )
    edited = await _edit_task(client, ada, plan, "a", 2, title="X")
    with pytest.raises(PlanNotEditableError):
        await save(app_sessions, ada, idea["id"], spec_id)

    assert_problem(phases, 409, "plan.invalid_transition")
    assert_problem(edited, 409, "plan.invalid_transition")


async def test_two_simultaneous_ready_calls_emit_one_event(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    responses = await asyncio.gather(
        client.post(plan_url(plan.id, "/ready"), headers=ada.headers),
        client.post(plan_url(plan.id, "/ready"), headers=ada.headers),
    )

    assert [r.status_code for r in responses] == [200, 200]
    assert len(await plan_ready_events(engine, ada)) == 1


async def test_two_phase_edits_on_one_version_one_wins_and_one_conflicts(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)
    first, second = plan.phases[0].id, plan.phases[1].id

    responses = await asyncio.gather(
        _edit_phases(
            client, ada, plan.id, 1, {"op": "rename", "phase_id": str(first), "name": "A"}
        ),
        _edit_phases(
            client, ada, plan.id, 1, {"op": "rename", "phase_id": str(second), "name": "B"}
        ),
    )

    assert sorted(r.status_code for r in responses) == [200, 409]


async def test_a_plan_cannot_grow_past_twelve_phases(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)
    spec_id = await latest_spec_id(client, ada, idea["id"])
    plan = await save(
        app_sessions, ada, idea["id"], spec_id, plan_input(phases=12, tasks=[task("a")])
    )

    response = await _edit_phases(
        client,
        ada,
        plan.id,
        1,
        {"op": "add", "name": "One more", "goal": "g", "exit_criteria": "e"},
    )

    assert_problem(response, 422, "plan.invalid_plan")
    assert response.json()["meta"]["reason"] == "limit_exceeded"


async def test_a_plan_over_the_task_limit_is_refused(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)
    spec_id = await latest_spec_id(client, ada, idea["id"])
    too_many = [task(f"t{i}") for i in range(201)]

    with pytest.raises(InvalidPlanError) as error:
        await save(app_sessions, ada, idea["id"], spec_id, plan_input(too_many))

    assert (error.value.meta or {})["reason"] == "limit_exceeded"
