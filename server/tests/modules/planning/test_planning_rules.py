"""The pure rules of a plan: estimates, links, cycles, the critical path and layout edits."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from metis.core.errors import InvalidPlanError, PlanNotFoundError
from metis.modules.planning import (
    DepInput,
    InvalidPlanReason,
    Phase,
    PlanInput,
    Task,
    critical_path,
)
from metis.modules.planning.dto import AddPhase, RemovePhase, RenamePhase, ReorderPhases
from metis.modules.planning.helpers.graph import nodes_on_cycles
from metis.modules.planning.helpers.layout import Layout, PhaseDraft, apply_phase_ops, move_task
from metis.modules.planning.helpers.validation import check_plan_input
from tests.modules.planning.planning_helpers import dep, plan_input, task


def _reason(error: pytest.ExceptionInfo[InvalidPlanError]) -> tuple[str, list[str]]:
    meta = error.value.meta or {}
    return meta["reason"], meta["tasks"]


# ---------------------------------------------------------------------------- validation


def test_a_valid_plan_passes() -> None:
    check_plan_input(plan_input())


@pytest.mark.parametrize("estimate", [0, 4, 6, 13, -1])
def test_an_estimate_outside_the_fibonacci_set_names_the_task(estimate: int) -> None:
    data = plan_input([task("big", estimate=estimate)])

    with pytest.raises(InvalidPlanError) as error:
        check_plan_input(data)

    assert _reason(error) == ("bad_estimate", ["big"])


def test_work_above_eight_is_told_to_split() -> None:
    with pytest.raises(InvalidPlanError, match="Split work above 8"):
        check_plan_input(plan_input([task("big", estimate=13)]))


@pytest.mark.parametrize(
    ("deps", "reason"),
    [
        ([dep("a", "a")], "self_dependency"),
        ([dep("a", "ghost")], "unknown_task"),
        ([dep("ghost", "a")], "unknown_task"),
        ([dep("b", "a"), dep("b", "a")], "duplicate_dependency"),
    ],
)
def test_a_bad_dependency_is_refused(deps: list[DepInput], reason: str) -> None:
    data = plan_input([task("a"), task("b")], deps)

    with pytest.raises(InvalidPlanError) as error:
        check_plan_input(data)

    assert _reason(error)[0] == reason


def test_a_dependency_loop_names_the_tasks_in_it_only() -> None:
    tasks = [task(k) for k in "abcd"]
    data = plan_input(tasks, [dep("b", "a"), dep("c", "b"), dep("b", "c"), dep("d", "c")])

    with pytest.raises(InvalidPlanError) as error:
        check_plan_input(data)

    reason, named = _reason(error)
    assert reason == "dependency_cycle"
    assert sorted(named) == ["b", "c"]


def test_a_longer_loop_is_found() -> None:
    tasks = [task(k) for k in "abc"]
    data = plan_input(tasks, [dep("b", "a"), dep("c", "b"), dep("a", "c")])

    with pytest.raises(InvalidPlanError) as error:
        check_plan_input(data)

    assert _reason(error)[0] == "dependency_cycle"


def test_parents_that_loop_are_refused() -> None:
    data = plan_input([task("a", parent_key="b"), task("b", parent_key="a")])

    with pytest.raises(InvalidPlanError) as error:
        check_plan_input(data)

    assert _reason(error)[0] == "parent_cycle"


def test_a_parent_outside_the_plan_is_refused() -> None:
    with pytest.raises(InvalidPlanError) as error:
        check_plan_input(plan_input([task("a", parent_key="ghost")]))

    assert _reason(error)[0] == "unknown_task"


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (plan_input([task("a")], phases=0), "no_phases"),
        (plan_input([], phases=1), "no_tasks"),
        (plan_input([task("a"), task("a")]), "duplicate_key"),
        (plan_input([task("a", phase=2)], phases=2), "unknown_phase"),
        (plan_input([task("a", phase=-1)]), "unknown_phase"),
        (plan_input([task("a")], phases=13), "limit_exceeded"),
    ],
)
def test_a_malformed_plan_is_refused_with_its_reason(data: PlanInput, reason: str) -> None:
    with pytest.raises(InvalidPlanError) as error:
        check_plan_input(data)

    assert _reason(error)[0] == reason


def test_the_graph_helper_finds_nothing_in_a_dag() -> None:
    assert nodes_on_cycles("abc", [("a", "b"), ("b", "c"), ("a", "c")]) == []


# ----------------------------------------------------------------------- critical path


def _task(estimate: int, blocked_by: tuple[UUID, ...] = (), position: int = 0) -> Task:
    return Task(
        id=uuid4(),
        position=position,
        title="t",
        description="",
        estimate=estimate,
        labels=(),
        parent_task_id=None,
        blocked_by=blocked_by,
    )


def _phase(*tasks: Task) -> Phase:
    return Phase(id=uuid4(), position=0, name="p", goal="g", exit_criteria="e", tasks=tuple(tasks))


def test_a_plan_without_dependencies_has_its_largest_task_as_the_path() -> None:
    small, large = _task(2, position=0), _task(8, position=1)

    path = critical_path((_phase(small, large),))

    assert (path.task_ids, path.points) == ((large.id,), 8)


def test_a_tie_goes_to_the_task_that_comes_first_in_the_plan() -> None:
    first = _task(3, position=0)
    second = _task(5, (first.id,), position=1)
    lone = _task(8, position=2)

    path = critical_path((_phase(first, second, lone),))

    assert (path.task_ids, path.points) == ((first.id, second.id), 8)


def test_a_longer_chain_wins_and_comes_in_dependency_order() -> None:
    a = _task(2, position=0)
    b = _task(3, (a.id,), position=1)
    c = _task(5, (b.id,), position=2)
    d = _task(8, position=3)

    path = critical_path((_phase(a, b, c, d),))

    assert (path.task_ids, path.points) == ((a.id, b.id, c.id), 10)


def test_a_task_with_two_blockers_follows_the_heavier_branch() -> None:
    light = _task(1, position=0)
    heavy = _task(8, position=1)
    end = _task(2, (light.id, heavy.id), position=2)

    path = critical_path((_phase(light, heavy, end),))

    assert (path.task_ids, path.points) == ((heavy.id, end.id), 10)


def test_an_empty_plan_has_an_empty_path() -> None:
    assert critical_path(()).points == 0


# ------------------------------------------------------------------------------ layout


def _layout() -> tuple[Layout, list[UUID], list[UUID]]:
    phases = [PhaseDraft(uuid4(), f"P{i}", "g", "e") for i in range(3)]
    ids = [uuid4() for _ in range(4)]
    tasks = {phases[0].id: (ids[0], ids[1]), phases[1].id: (ids[2],), phases[2].id: (ids[3],)}
    return Layout(tuple(phases), tasks), [p.id for p in phases], ids


def test_rename_changes_only_the_fields_given() -> None:
    layout, phases, _ = _layout()

    after = apply_phase_ops(layout, [RenamePhase(op="rename", phase_id=phases[0], name="New")])

    assert (after.phases[0].name, after.phases[0].goal) == ("New", "g")
    assert layout.phases[0].name == "P0"  # the original is untouched


def test_reorder_needs_every_phase_exactly_once() -> None:
    layout, phases, _ = _layout()

    after = apply_phase_ops(
        layout, [ReorderPhases(op="reorder", phase_ids=tuple(reversed(phases)))]
    )
    assert after.phase_ids() == tuple(reversed(phases))
    with pytest.raises(InvalidPlanError):
        apply_phase_ops(layout, [ReorderPhases(op="reorder", phase_ids=tuple(phases[:2]))])


def test_add_puts_the_phase_at_the_position_or_last() -> None:
    layout, phases, _ = _layout()

    first = apply_phase_ops(
        layout, [AddPhase(op="add", name="N", goal="g", exit_criteria="e", position=0)]
    )
    last = apply_phase_ops(layout, [AddPhase(op="add", name="N", goal="g", exit_criteria="e")])

    assert first.phases[0].name == "N"
    assert last.phases[-1].name == "N"
    assert first.tasks[first.phases[0].id] == ()
    with pytest.raises(InvalidPlanError):
        apply_phase_ops(
            layout, [AddPhase(op="add", name="N", goal="g", exit_criteria="e", position=9)]
        )


def test_removing_a_phase_moves_its_tasks_to_the_end_of_another() -> None:
    layout, phases, ids = _layout()

    after = apply_phase_ops(
        layout, [RemovePhase(op="remove", phase_id=phases[0], move_tasks_to=phases[1])]
    )

    assert after.phase_ids() == (phases[1], phases[2])
    assert after.tasks[phases[1]] == (ids[2], ids[0], ids[1])


def test_removing_a_phase_with_tasks_needs_a_target() -> None:
    layout, phases, _ = _layout()

    with pytest.raises(InvalidPlanError):
        apply_phase_ops(layout, [RemovePhase(op="remove", phase_id=phases[0])])


def test_the_only_phase_cannot_be_removed() -> None:
    phase = PhaseDraft(uuid4(), "P", "g", "e")
    layout = Layout((phase,), {phase.id: ()})

    with pytest.raises(InvalidPlanError):
        apply_phase_ops(layout, [RemovePhase(op="remove", phase_id=phase.id)])


def test_an_unknown_phase_is_not_found() -> None:
    layout, _, _ = _layout()

    with pytest.raises(PlanNotFoundError):
        apply_phase_ops(layout, [RemovePhase(op="remove", phase_id=uuid4())])


def test_a_task_moves_to_another_phase_last_by_default() -> None:
    layout, phases, ids = _layout()

    after = move_task(layout, ids[0], phases[1], None)

    assert after.tasks[phases[0]] == (ids[1],)
    assert after.tasks[phases[1]] == (ids[2], ids[0])


def test_a_task_moves_inside_its_phase() -> None:
    layout, phases, ids = _layout()

    after = move_task(layout, ids[0], None, 1)

    assert after.tasks[phases[0]] == (ids[1], ids[0])
    with pytest.raises(InvalidPlanError):
        move_task(layout, ids[0], phases[1], 5)


def test_the_reason_enum_covers_every_meta_value() -> None:
    assert {r.value for r in InvalidPlanReason} >= {"dependency_cycle", "bad_estimate"}
