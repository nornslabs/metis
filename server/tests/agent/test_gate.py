"""The shared gate: code checks, judge, retries, skip, fail-open, cap, events and spans."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from metis.agent import gate as gate_module
from metis.agent.gate import (
    MAX_REASON_CHARS,
    Gate,
    GateContext,
    GateDecisionKind,
    GateRefusal,
    ModelJudge,
    enforce_gate,
    run_gate,
)
from metis.agent.specialists.base import build_react_specialist
from tests.agent.test_specialist_base import FakeChat

NOT_EMPTY = "item is empty"


def _not_empty(item: Any) -> str | None:
    return None if item else NOT_EMPTY


class FakeJudge:
    def __init__(self, *verdicts: str | None | Exception) -> None:
        self._verdicts = list(verdicts)
        self.calls = 0

    async def verdict(self, instruction: str, item: str) -> str | None:
        self.calls += 1
        outcome = self._verdicts.pop(0) if len(self._verdicts) > 1 else self._verdicts[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeBudget:
    def __init__(self, allowed: int) -> None:
        self._allowed = allowed

    async def take(self) -> bool:
        self._allowed -= 1
        return self._allowed >= 0


class Recorder:
    def __init__(self) -> None:
        self.events: list[Mapping[str, Any]] = []

    def __call__(self, event: Mapping[str, Any]) -> None:
        self.events.append(event)


def _context(
    judge: FakeJudge | None, recorder: Recorder, budget: FakeBudget | None = None
) -> GateContext:
    return GateContext(judge=judge, budget=budget, emit=recorder)  # type: ignore[arg-type]


CODE_GATE = Gate(name="question", specialist="interviewer", checks=(_not_empty,))
JUDGED_GATE = Gate(
    name="question", specialist="interviewer", checks=(_not_empty,), judge_instruction="Be kind."
)


async def test_a_failing_code_check_rejects_without_a_judge_call() -> None:
    judge, recorder = FakeJudge(None), Recorder()

    decision = await run_gate(JUDGED_GATE, "q1", "", _context(judge, recorder))

    assert decision.kind is GateDecisionKind.RETRIED and decision.reason == NOT_EMPTY
    assert judge.calls == 0


async def test_an_item_that_passes_every_check_and_the_judge_passes() -> None:
    judge, recorder = FakeJudge(None), Recorder()

    decision = await run_gate(
        JUDGED_GATE, "q1", "What are you building?", _context(judge, recorder)
    )

    assert decision.kind is GateDecisionKind.PASSED
    assert judge.calls == 1


async def test_a_judge_rejection_is_retried_then_passes_on_a_revision() -> None:
    judge, recorder = FakeJudge("too blunt", None), Recorder()
    context = _context(judge, recorder)

    first = await run_gate(JUDGED_GATE, "q1", "Why?", context)
    second = await run_gate(JUDGED_GATE, "q1", "What led you here?", context)

    assert (first.kind, first.reason) == (GateDecisionKind.RETRIED, "too blunt")
    assert second.kind is GateDecisionKind.PASSED


async def test_after_two_retries_the_third_rejection_skips_the_item() -> None:
    recorder = Recorder()
    context = _context(None, recorder)

    kinds = [(await run_gate(CODE_GATE, "q1", "", context)).kind for _ in range(3)]

    assert kinds == [
        GateDecisionKind.RETRIED,
        GateDecisionKind.RETRIED,
        GateDecisionKind.SKIPPED,
    ]


async def test_each_item_keeps_its_own_attempts() -> None:
    context = _context(None, Recorder())
    await run_gate(CODE_GATE, "q1", "", context)
    await run_gate(CODE_GATE, "q1", "", context)

    other = await run_gate(CODE_GATE, "q2", "", context)

    assert other.kind is GateDecisionKind.RETRIED


@pytest.mark.parametrize(
    "judge",
    [FakeJudge(RuntimeError("boom")), FakeJudge(TimeoutError())],
)
async def test_a_judge_error_lets_the_item_through(judge: FakeJudge) -> None:
    decision = await run_gate(JUDGED_GATE, "q1", "ok", _context(judge, Recorder()))

    assert decision.kind is GateDecisionKind.PASSED


async def test_an_exhausted_judge_cap_lets_the_item_through_but_code_checks_still_run() -> None:
    judge, recorder = FakeJudge("never asked"), Recorder()
    context = _context(judge, recorder, FakeBudget(0))

    passed = await run_gate(JUDGED_GATE, "q1", "ok", context)
    rejected = await run_gate(JUDGED_GATE, "q2", "", context)

    assert passed.kind is GateDecisionKind.PASSED and judge.calls == 0
    assert rejected.kind is GateDecisionKind.RETRIED


@pytest.mark.parametrize(
    ("reply", "expected"),
    [("PASS", None), ("pass\n", None), ("REJECT: too long", "too long")],
)
async def test_the_model_judge_reads_pass_and_reject_lines(
    reply: str, expected: str | None
) -> None:
    judge = ModelJudge(FakeChat([AIMessage(content=reply)]))

    assert await judge.verdict("criterion", "item") == expected


@pytest.mark.parametrize("reply", ["", "maybe", "REJECT:"])
async def test_an_unreadable_judge_reply_raises_so_the_gate_fails_open(reply: str) -> None:
    judge = ModelJudge(FakeChat([AIMessage(content=reply)]))

    with pytest.raises(ValueError, match="unreadable"):
        await judge.verdict("criterion", "item")
    decision = await run_gate(JUDGED_GATE, "q1", "ok", GateContext(judge=judge, budget=None))
    assert decision.kind is GateDecisionKind.PASSED


async def test_every_decision_emits_one_gate_event_and_one_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spans: list[Mapping[str, str]] = []
    monkeypatch.setattr(
        gate_module, "record_gate_span", lambda _settings, fields: spans.append(fields)
    )
    recorder = Recorder()
    context = _context(None, recorder)

    for _ in range(3):
        await run_gate(CODE_GATE, "q1", "", context)
    await run_gate(CODE_GATE, "q2", "fine", context)

    assert [e["decision"] for e in recorder.events] == ["retried", "retried", "skipped", "passed"]
    assert recorder.events[0] == {
        "type": "gate",
        "specialist": "interviewer",
        "gate": "question",
        "decision": "retried",
        "reason": NOT_EMPTY,
    }
    assert [s["decision"] for s in spans] == [e["decision"] for e in recorder.events]


async def test_the_reason_is_cut_at_the_limit() -> None:
    long_gate = Gate(name="g", specialist="s", checks=(lambda _item: "x" * 500,))
    recorder = Recorder()

    await run_gate(long_gate, "k", "item", _context(None, recorder))

    assert len(recorder.events[0]["reason"]) == MAX_REASON_CHARS


async def test_a_failing_event_sink_does_not_change_the_decision() -> None:
    def broken(_event: Mapping[str, Any]) -> None:
        raise RuntimeError("no stream")

    decision = await run_gate(
        CODE_GATE, "q1", "", GateContext(judge=None, budget=None, emit=broken)
    )

    assert decision.kind is GateDecisionKind.RETRIED


async def test_enforce_raises_a_refusal_while_the_model_may_revise() -> None:
    context = _context(None, Recorder())

    with pytest.raises(GateRefusal, match=NOT_EMPTY):
        await enforce_gate(CODE_GATE, "q1", "", context)


async def test_a_tool_loop_skips_a_stubborn_item_and_finishes_without_failing() -> None:
    context = _context(None, Recorder())

    @tool
    async def ask(text: str) -> str:
        """Ask the user a question."""
        decision = await enforce_gate(CODE_GATE, "q1", "", context)
        return "skipped: continue without it" if decision.kind is GateDecisionKind.SKIPPED else text

    call = AIMessage(content="", tool_calls=[{"name": "ask", "args": {"text": ""}, "id": "c"}])
    chat = FakeChat([call, call, call, AIMessage(content="done")])
    loop = build_react_specialist("p", [ask], chat, refusals=(GateRefusal,))

    result = await loop.ainvoke({"messages": [HumanMessage(content="go")]})

    tool_results = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.status for m in tool_results] == ["error", "error", "success"]
    assert NOT_EMPTY in str(tool_results[0].content)
    assert result["messages"][-1].content == "done"
