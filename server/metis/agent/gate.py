"""The shared gate: a check an item must pass before a specialist may use it.

A **gate** is a name, its specialist, ordered code checks and an optional judge instruction.
``run_gate`` reviews one item: code checks first (a failing check rejects without a judge
call), then the judge, a cheaper model reached through the LLM gateway with purpose ``gate``.

A rejection is returned to the model as a refusal (``GateRefusal``, listed in a specialist's
``refusals``), so it may revise the item. After ``MAX_RETRIES`` rejected revisions the item is
skipped: the specialist goes on without it. A skip is a valid outcome, never a failure, so
nothing here raises into the run or sets ``last_error``.

The judge fails open: its own error, an unreadable reply or an exhausted per-run cap lets the
item through. Code checks never fail open.

Every decision (``passed``, ``retried``, ``skipped``) is published as one ``gate`` run event
and recorded as one trace span, both with ``{specialist, gate, decision, reason}``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.config import get_stream_writer
from langgraph.constants import TAG_NOSTREAM
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from metis.agent.llm import LLMGateway
from metis.agent.prompts import load_prompt
from metis.agent.tracing import record_gate_span
from metis.core.config import get_settings
from metis.core.events import RunEventType
from metis.core.logging import get_logger
from metis.core.ports import LLMProvider

MAX_RETRIES = 2
MAX_REASON_CHARS = 200
JUDGE_PROMPT = "gate_judge"
JUDGE_PURPOSE = "gate"
JUDGE_COUNTER_TTL_SECONDS = 24 * 3600
JUDGE_UNAVAILABLE = "judge unavailable"

logger = get_logger(__name__)

CodeCheck = Callable[[Any], str | None]
"""Returns ``None`` when the item passes, or the reason it is rejected."""


class GateDecisionKind(StrEnum):
    PASSED = "passed"
    RETRIED = "retried"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class Gate:
    """One specialist's check: code checks in order, then an optional judge instruction."""

    name: str
    specialist: str
    checks: tuple[CodeCheck, ...] = ()
    judge_instruction: str | None = None


@dataclass(frozen=True)
class GateDecision:
    kind: GateDecisionKind
    reason: str


class GateRefusal(Exception):
    """An item was rejected and may be revised; list it in a specialist's ``refusals``."""


class Judge(Protocol):
    async def verdict(self, instruction: str, item: str) -> str | None:
        """``None`` to pass the item, or the reason to reject it. Raises on its own errors."""
        ...


class ModelJudge:
    """A judge over a chat model (the gateway's ``gate`` purpose)."""

    def __init__(self, model: LLMProvider) -> None:
        self._model = model

    async def verdict(self, instruction: str, item: str) -> str | None:
        reply = await self._model.ainvoke(
            [
                SystemMessage(content=load_prompt(JUDGE_PROMPT)),
                HumanMessage(content=f"Criterion:\n{instruction}\n\nItem:\n{item}"),
            ],
            # Prevent LangGraph's ``messages`` stream mode from forwarding judge tokens
            # (e.g. "PASS") to the UI.
            config={"tags": [TAG_NOSTREAM]},
        )
        return _parse_verdict(reply.text)


class JudgeBudget:
    """Judge calls a run may make, counted in Redis so a resumed run keeps its count."""

    def __init__(self, redis: Redis, run_id: UUID, limit: int) -> None:
        self._redis = redis
        self._key = f"agent:gate:{run_id}:judge_calls"
        self._limit = limit

    async def take(self) -> bool:
        """Spend one judge call; ``False`` once the limit is reached."""
        used = await self._redis.incr(self._key)
        await self._redis.expire(self._key, JUDGE_COUNTER_TTL_SECONDS)
        return int(used) <= self._limit


@dataclass
class GateContext:
    """What a gate run needs: the judge, its budget, and where decisions are reported.

    ``attempts`` counts rejections per ``(gate, item key)``; it lives as long as the context,
    so one specialist invocation keeps one context.
    """

    judge: Judge | None
    budget: JudgeBudget | None
    emit: Callable[[Mapping[str, Any]], None] = field(default=lambda event: _stream(event))
    attempts: dict[tuple[str, str], int] = field(default_factory=dict)


async def run_gate(gate: Gate, key: str, item: Any, context: GateContext) -> GateDecision:
    """Review ``item`` (identified by ``key`` among the items of this gate) and report it."""
    reason = _failing_check(gate, item)
    if reason is None:
        reason = await _judge_rejection(gate, item, context)
    decision = _decide(gate, key, reason, context)
    _report(gate, decision, context)
    return decision


async def enforce_gate(gate: Gate, key: str, item: Any, context: GateContext) -> GateDecision:
    """``run_gate``, raising ``GateRefusal`` (the reason) when the model may revise the item.

    Returns the decision for ``passed`` and ``skipped``; a tool turns ``skipped`` into an
    answer that tells the model to continue without the item.
    """
    decision = await run_gate(gate, key, item, context)
    if decision.kind is GateDecisionKind.RETRIED:
        raise GateRefusal(decision.reason)
    return decision


async def build_gate_context(
    gateway: LLMGateway, session: AsyncSession, redis: Redis, run_id: UUID
) -> GateContext:
    """A context whose judge runs on the gateway's ``gate`` model, capped per run by settings."""
    model = await gateway.chat_model(session, JUDGE_PURPOSE)
    budget = JudgeBudget(redis, run_id, get_settings().gate_judge_max_calls_per_run)
    return GateContext(judge=ModelJudge(model), budget=budget)


def _failing_check(gate: Gate, item: Any) -> str | None:
    for check in gate.checks:
        reason = check(item)
        if reason is not None:
            return reason
    return None


async def _judge_rejection(gate: Gate, item: Any, context: GateContext) -> str | None:
    """The judge's reason to reject, or ``None`` to pass (also when the judge is unavailable)."""
    if gate.judge_instruction is None or context.judge is None:
        return None
    if context.budget is not None and not await _take_budget(gate, context.budget):
        return None
    try:
        return await context.judge.verdict(gate.judge_instruction, _as_text(item))
    except Exception:  # noqa: BLE001  (the judge fails open on any error of its own)
        logger.warning("gate.judge_failed", gate=gate.name, specialist=gate.specialist)
        return None


async def _take_budget(gate: Gate, budget: JudgeBudget) -> bool:
    try:
        spent = await budget.take()
    except Exception:  # noqa: BLE001  (a lost counter must not block the item)
        logger.warning("gate.judge_budget_failed", gate=gate.name)
        return False
    if not spent:
        logger.info("gate.judge_cap_reached", gate=gate.name, specialist=gate.specialist)
    return spent


def _decide(gate: Gate, key: str, reason: str | None, context: GateContext) -> GateDecision:
    if reason is None:
        return GateDecision(GateDecisionKind.PASSED, "passed")
    slot = (gate.name, key)
    rejections = context.attempts.get(slot, 0) + 1
    context.attempts[slot] = rejections
    kind = GateDecisionKind.RETRIED if rejections <= MAX_RETRIES else GateDecisionKind.SKIPPED
    return GateDecision(kind, reason)


def _report(gate: Gate, decision: GateDecision, context: GateContext) -> None:
    fields = {
        "specialist": gate.specialist,
        "gate": gate.name,
        "decision": decision.kind.value,
        "reason": decision.reason[:MAX_REASON_CHARS],
    }
    try:
        context.emit({"type": RunEventType.GATE.value, **fields})
    except Exception:  # noqa: BLE001  (reporting must never change a gate's outcome)
        logger.warning("gate.event_failed", gate=gate.name)
    record_gate_span(get_settings(), fields)


def _parse_verdict(text: str) -> str | None:
    """``None`` for ``PASS``, the reason for ``REJECT: ...``; else raises ``ValueError``."""
    line = text.strip().splitlines()[0].strip() if text.strip() else ""
    if line.upper() == "PASS":
        return None
    head, _, reason = line.partition(":")
    if head.strip().upper() == "REJECT" and reason.strip():
        return reason.strip()
    raise ValueError("unreadable judge reply")


def _as_text(item: Any) -> str:
    return item if isinstance(item, str) else json.dumps(item, default=str, ensure_ascii=False)


def _stream(event: Mapping[str, Any]) -> None:
    get_stream_writer()(dict(event))
